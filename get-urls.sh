#!/bin/bash

echo "🔍 Finding Your Deployment URLs..."
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"

echo "AWS Account: $ACCOUNT_ID"
echo "Region: $REGION"
echo ""
echo "================================"
echo ""

# Check for Load Balancers
echo -e "${BLUE}🔍 Checking for Load Balancers...${NC}"
LB_DNS=$(aws elbv2 describe-load-balancers \
  --region $REGION \
  --query 'LoadBalancers[?contains(LoadBalancerName, `trace`)].DNSName' \
  --output text 2>/dev/null)

if [ -n "$LB_DNS" ]; then
    echo -e "${GREEN}✓ Backend API URL found:${NC}"
    echo -e "  ${GREEN}http://$LB_DNS${NC}"
    echo ""
    echo "Test it:"
    echo "  curl http://$LB_DNS/health"
else
    echo -e "${YELLOW}! No load balancer found yet${NC}"
fi

echo ""
echo "================================"
echo ""

# Check for CloudFront
echo -e "${BLUE}🔍 Checking for CloudFront...${NC}"
CF_DOMAIN=$(aws cloudfront list-distributions \
  --query 'DistributionList.Items[?contains(Comment, `trace`) || contains(Comment, `frontend`)].DomainName' \
  --output text 2>/dev/null | head -1)

if [ -n "$CF_DOMAIN" ]; then
    echo -e "${GREEN}✓ Frontend URL found:${NC}"
    echo -e "  ${GREEN}https://$CF_DOMAIN${NC}"
    echo ""
    echo "Open in browser:"
    echo "  open https://$CF_DOMAIN"
else
    echo -e "${YELLOW}! No CloudFront distribution found yet${NC}"
fi

echo ""
echo "================================"
echo ""

# Check for S3 static website
echo -e "${BLUE}🔍 Checking for S3 static website...${NC}"
S3_WEBSITE=$(aws s3api list-buckets \
  --query 'Buckets[?contains(Name, `trace-frontend`)].Name' \
  --output text 2>/dev/null)

if [ -n "$S3_WEBSITE" ]; then
    echo -e "${GREEN}✓ S3 bucket found: $S3_WEBSITE${NC}"
    echo "  URL: http://$S3_WEBSITE.s3-website-$REGION.amazonaws.com"
else
    echo -e "${YELLOW}! No S3 static website found yet${NC}"
fi

echo ""
echo "================================"
echo ""

# Check ECS Services
echo -e "${BLUE}🔍 Checking ECS Services...${NC}"
ECS_SERVICES=$(aws ecs list-services \
  --cluster trace-cluster \
  --region $REGION \
  --query 'serviceArns' \
  --output text 2>/dev/null)

if [ -n "$ECS_SERVICES" ]; then
    echo -e "${GREEN}✓ ECS Services found:${NC}"
    for service in $ECS_SERVICES; do
        service_name=$(basename $service)
        echo "  - $service_name"
    done
else
    echo -e "${YELLOW}! No ECS services found yet${NC}"
    echo "  Run: aws ecs list-clusters"
fi

echo ""
echo "================================"
echo ""

# Summary
echo -e "${BLUE}📋 Summary:${NC}"
echo ""

if [ -n "$LB_DNS" ]; then
    echo -e "${GREEN}Backend API:${NC}  http://$LB_DNS"
else
    echo -e "${YELLOW}Backend API:${NC}  Not deployed yet"
fi

if [ -n "$CF_DOMAIN" ]; then
    echo -e "${GREEN}Frontend:${NC}     https://$CF_DOMAIN"
elif [ -n "$S3_WEBSITE" ]; then
    echo -e "${GREEN}Frontend:${NC}     http://$S3_WEBSITE.s3-website-$REGION.amazonaws.com"
else
    echo -e "${YELLOW}Frontend:${NC}     Not deployed yet"
fi

echo ""

# Save to file
if [ -n "$LB_DNS" ] || [ -n "$CF_DOMAIN" ]; then
    cat > deployment-urls.txt << EOF
Backend API: http://$LB_DNS
Frontend: https://$CF_DOMAIN

Generated: $(date)
EOF
    echo -e "${GREEN}✓ URLs saved to deployment-urls.txt${NC}"
fi

echo ""
echo "To deploy, run:"
echo "  1. ./create-ecr.sh"
echo "  2. ./build-and-push.sh"
echo "  3. Push to GitHub (GitHub Actions will deploy)"
echo ""
