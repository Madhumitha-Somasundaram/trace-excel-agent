#!/bin/bash

echo "🚀 Quick Deploy Script for Trace Excel Agent"
echo "=============================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Check Git
echo "📋 Step 1: Checking Git status..."
if [ -d .git ]; then
    echo -e "${GREEN}✓ Git repository exists${NC}"
else
    echo -e "${YELLOW}! Initializing Git repository...${NC}"
    git init
fi

# Step 2: Add files
echo ""
echo "📋 Step 2: Adding files to Git..."
echo "Adding Dockerfiles..."
git add Dockerfile.backend Dockerfile.frontend Dockerfile.worker docker-compose.yml nginx.conf .gitignore

echo "Adding CI/CD pipeline..."
git add .github/ 2>/dev/null || echo "  (GitHub workflows will be added)"

echo "Adding backend..."
git add backend/models/ backend/auth/ backend/app/ backend/tools/ backend/agent_runtime/ backend/scripts/ 2>/dev/null
git add backend/requirements.txt backend/requirements-worker.txt backend/ec2_sqs_worker.py 2>/dev/null

echo "Adding frontend..."
git add frontend/src/ frontend/public/ frontend/package.json 2>/dev/null

echo "Adding documentation..."
git add *.md 2>/dev/null

echo -e "${GREEN}✓ Files staged${NC}"

# Step 3: Commit
echo ""
echo "📋 Step 3: Committing changes..."
git commit -m "Add authentication and cloud deployment setup" 2>/dev/null || echo -e "${YELLOW}! No changes to commit${NC}"

# Step 4: Generate JWT Secret
echo ""
echo "📋 Step 4: Generating JWT Secret..."
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo -e "${GREEN}✓ JWT Secret generated${NC}"
echo ""
echo -e "${YELLOW}Your JWT Secret:${NC}"
echo -e "${GREEN}$JWT_SECRET${NC}"
echo ""
echo "Save this! You'll need it for GitHub secrets."

# Step 5: Check AWS credentials
echo ""
echo "📋 Step 5: Checking AWS credentials..."
if aws sts get-caller-identity &>/dev/null; then
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    echo -e "${GREEN}✓ AWS credentials configured${NC}"
    echo "  Account ID: $ACCOUNT_ID"
else
    echo -e "${RED}✗ AWS credentials not configured${NC}"
    echo "Run: aws configure"
    exit 1
fi

# Step 6: Create .env.production
echo ""
echo "📋 Step 6: Creating .env.production file..."
cat > .env.production << EOF
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=$ACCOUNT_ID

# JWT Secret
JWT_SECRET_KEY=$JWT_SECRET

# Google OAuth (get from Google Cloud Console)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Database
DYNAMODB_TABLE_USERS=users
DYNAMODB_TABLE_JOBS=jobs

# Storage
S3_BUCKET=excel-trace-agent-bucket-$ACCOUNT_ID
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/$ACCOUNT_ID/excel-trace-queue
EOF

echo -e "${GREEN}✓ .env.production created${NC}"

# Summary
echo ""
echo "=============================================="
echo -e "${GREEN}✅ Ready for deployment!${NC}"
echo "=============================================="
echo ""
echo "Next steps:"
echo ""
echo "1️⃣  Create GitHub Repository:"
echo "   - Go to: https://github.com/new"
echo "   - Name: trace-excel-agent"
echo "   - Make it Private"
echo "   - Click 'Create repository'"
echo ""
echo "2️⃣  Add GitHub Secrets:"
echo "   - Go to: Settings → Secrets → Actions → New secret"
echo "   - Add these secrets:"
echo ""
echo "   AWS_ACCESS_KEY_ID"
echo "   AWS_SECRET_ACCESS_KEY"
echo "   JWT_SECRET_KEY = $JWT_SECRET"
echo "   AWS_ACCOUNT_ID = $ACCOUNT_ID"
echo ""
echo "3️⃣  Push to GitHub:"
echo "   git remote add origin https://github.com/YOUR_USERNAME/trace-excel-agent.git"
echo "   git branch -M main"
echo "   git push -u origin main"
echo ""
echo "4️⃣  Create ECR Repositories:"
echo "   ./create-ecr.sh"
echo ""
echo "5️⃣  Build and Deploy:"
echo "   ./build-and-push.sh"
echo ""
echo "📖 For detailed instructions, see: DEPLOY_STEP_BY_STEP.md"
echo ""
