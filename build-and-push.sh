#!/bin/bash

echo "🐳 Building and Pushing Docker Images..."
echo ""

# Get AWS Account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "Account ID: $ACCOUNT_ID"
echo "Region: $REGION"
echo ""

# Login to ECR
echo "Logging in to ECR..."
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Logged in to ECR${NC}"
else
    echo -e "${RED}✗ ECR login failed${NC}"
    exit 1
fi

echo ""

# Build Backend
echo "🏗️  Building backend image..."
docker build -t trace-backend:latest -f Dockerfile.backend .
docker tag trace-backend:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-backend:latest
echo -e "${GREEN}✓ Backend image built${NC}"

# Build Worker
echo "🏗️  Building worker image..."
docker build -t trace-worker:latest -f Dockerfile.worker .
docker tag trace-worker:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-worker:latest
echo -e "${GREEN}✓ Worker image built${NC}"

# Build Frontend
echo "🏗️  Building frontend image..."
docker build -t trace-frontend:latest -f Dockerfile.frontend .
docker tag trace-frontend:latest $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-frontend:latest
echo -e "${GREEN}✓ Frontend image built${NC}"

echo ""

# Push images
echo "📤 Pushing images to ECR..."
echo ""

echo "Pushing backend..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-backend:latest
echo -e "${GREEN}✓ Backend pushed${NC}"

echo "Pushing worker..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-worker:latest
echo -e "${GREEN}✓ Worker pushed${NC}"

echo "Pushing frontend..."
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-frontend:latest
echo -e "${GREEN}✓ Frontend pushed${NC}"

echo ""
echo -e "${GREEN}✅ All images built and pushed successfully!${NC}"
echo ""
echo "Image URLs:"
echo "Backend:  $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-backend:latest"
echo "Worker:   $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-worker:latest"
echo "Frontend: $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/trace-frontend:latest"
echo ""
echo "Next steps:"
echo "1. Create ECS cluster and services"
echo "2. Or push to GitHub for automatic deployment"
