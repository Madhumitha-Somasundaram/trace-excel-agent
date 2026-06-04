#!/bin/bash

echo "🏗️  Creating ECR Repositories..."
echo ""

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Create repositories
echo "Creating trace-backend repository..."
aws ecr create-repository \
  --repository-name trace-backend \
  --region $REGION \
  --image-scanning-configuration scanOnPush=true \
  2>/dev/null && echo -e "${GREEN}✓ trace-backend created${NC}" || echo -e "${YELLOW}! trace-backend already exists${NC}"

echo "Creating trace-worker repository..."
aws ecr create-repository \
  --repository-name trace-worker \
  --region $REGION \
  --image-scanning-configuration scanOnPush=true \
  2>/dev/null && echo -e "${GREEN}✓ trace-worker created${NC}" || echo -e "${YELLOW}! trace-worker already exists${NC}"

echo "Creating trace-frontend repository..."
aws ecr create-repository \
  --repository-name trace-frontend \
  --region $REGION \
  --image-scanning-configuration scanOnPush=true \
  2>/dev/null && echo -e "${GREEN}✓ trace-frontend created${NC}" || echo -e "${YELLOW}! trace-frontend already exists${NC}"

echo ""
echo "ECR Repository URLs:"
echo "Backend:  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-backend"
echo "Worker:   $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-worker"
echo "Frontend: $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-frontend"
echo ""
echo -e "${GREEN}✅ ECR repositories ready!${NC}"
echo ""
echo "Next: Run ./build-and-push.sh to build and push Docker images"
