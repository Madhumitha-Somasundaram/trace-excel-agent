# 🚀 Complete Deployment Guide - Step by Step

Follow these exact steps to deploy your application to the cloud.

---

## ✅ STEP 1: Add Files to Git (5 minutes)

```bash
cd /Users/madhumithas/Downloads/Projects/Trace

# Add Dockerfiles
git add Dockerfile.backend Dockerfile.frontend Dockerfile.worker
git add docker-compose.yml nginx.conf .gitignore

# Add CI/CD
git add .github/

# Add backend
git add backend/models/ backend/auth/ backend/app/
git add backend/tools/ backend/agent_runtime/ backend/scripts/
git add backend/requirements.txt backend/requirements-worker.txt
git add backend/ec2_sqs_worker.py

# Add frontend  
git add frontend/src/ frontend/public/
git add frontend/package.json package-lock.json

# Add docs
git add DEPLOYMENT_GUIDE.md START_HERE.md AUTH_SUMMARY.md

# Commit
git commit -m "Add authentication and cloud deployment setup"
```

---

## ✅ STEP 2: Create GitHub Repository (5 minutes)

### Option A: Using GitHub Website

1. Go to https://github.com/new
2. Repository name: `trace-excel-agent`
3. Description: `Excel Trace Agent with AI-powered processing`
4. Keep it **Private** (recommended)
5. Don't initialize with README (we already have one)
6. Click **Create repository**

### Option B: Using GitHub CLI

```bash
# Install GitHub CLI (if not installed)
brew install gh

# Login
gh auth login

# Create repo
gh repo create trace-excel-agent --private --source=. --remote=origin
```

### Push to GitHub

```bash
# Add remote (if using Option A)
git remote add origin https://github.com/YOUR_USERNAME/trace-excel-agent.git

# Push code
git branch -M main
git push -u origin main
```

---

## ✅ STEP 3: Set Up Environment Variables (10 minutes)

### 3.1 Generate JWT Secret

```bash
# Generate a secure JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Example output: 
# xK9_mP3nQ7wR2tY8vZ5aB4cD1eF6gH0iJ
```

**Save this!** You'll need it for GitHub secrets.

### 3.2 Get Your AWS Credentials

```bash
# If AWS CLI is configured
cat ~/.aws/credentials

# You'll see:
# [default]
# aws_access_key_id = AKIA...
# aws_secret_access_key = abc123...
```

If not configured:
```bash
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key  
# Enter region: us-east-1
# Enter output format: json
```

### 3.3 Create `.env.production` File

```bash
cat > .env.production << 'EOF'
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=YOUR_ACCOUNT_ID

# JWT Secret (from Step 3.1)
JWT_SECRET_KEY=YOUR_GENERATED_SECRET_HERE

# Google OAuth (optional - get from Google Cloud Console)
GOOGLE_CLIENT_ID=your-google-client-id-here
GOOGLE_CLIENT_SECRET=your-google-client-secret-here

# Database
DYNAMODB_TABLE_USERS=users
DYNAMODB_TABLE_JOBS=jobs

# Storage
S3_BUCKET=excel-trace-agent-bucket-549955691461
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/549955691461/excel-trace-queue

# API URLs (will be updated after deployment)
BACKEND_URL=https://api.yourdomain.com
FRONTEND_URL=https://yourdomain.com
EOF
```

**Important:** This file should NOT be committed to Git (it's in .gitignore)

---

## ✅ STEP 4: Add GitHub Secrets (5 minutes)

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add these secrets one by one:

### Required Secrets:

| Secret Name | Value | Where to find |
|-------------|-------|---------------|
| `AWS_ACCESS_KEY_ID` | `AKIA...` | From Step 3.2 |
| `AWS_SECRET_ACCESS_KEY` | `abc123...` | From Step 3.2 |
| `JWT_SECRET_KEY` | `xK9_mP3n...` | From Step 3.1 |
| `AWS_ACCOUNT_ID` | `123456789012` | Run: `aws sts get-caller-identity --query Account --output text` |

### Optional Secrets (for production):

| Secret Name | Value | Note |
|-------------|-------|------|
| `CLOUDFRONT_DISTRIBUTION_ID` | `E1ABC2DEF3GHI` | After CloudFront is created |
| `GOOGLE_CLIENT_ID` | Your Google OAuth ID | If using Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Your Google OAuth secret | If using Google OAuth |

---

## ✅ STEP 5: Deploy Infrastructure (15 minutes)

### Option A: Manual AWS Setup (Quick Start)

The easiest way to get started - create resources manually:

#### 5.1 Create ECR Repositories

```bash
# Backend repository
aws ecr create-repository \
  --repository-name trace-backend \
  --region us-east-1

# Worker repository  
aws ecr create-repository \
  --repository-name trace-worker \
  --region us-east-1

# Frontend repository
aws ecr create-repository \
  --repository-name trace-frontend \
  --region us-east-1

# Save the URLs from output
```

#### 5.2 Create ECS Cluster

```bash
aws ecs create-cluster \
  --cluster-name trace-cluster \
  --region us-east-1
```

#### 5.3 Build and Push Images

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

# Build images
docker build -t trace-backend:latest -f Dockerfile.backend .
docker build -t trace-worker:latest -f Dockerfile.worker .
docker build -t trace-frontend:latest -f Dockerfile.frontend .

# Tag images
docker tag trace-backend:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trace-backend:latest

docker tag trace-worker:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trace-worker:latest

docker tag trace-frontend:latest \
  YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trace-frontend:latest

# Push images
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trace-backend:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trace-worker:latest
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trace-frontend:latest
```

### Option B: Terraform (Automated)

For full infrastructure automation:

```bash
cd infrastructure/terraform

# Initialize Terraform
terraform init

# Preview changes
terraform plan

# Deploy infrastructure
terraform apply -auto-approve

# Save outputs
terraform output > ../../deployment-outputs.txt
```

---

## ✅ STEP 6: Get Your URLs (After Deployment)

### Backend API URL

#### If using ALB (Application Load Balancer):

```bash
# Get backend URL
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[?contains(LoadBalancerName, `trace-backend`)].DNSName' \
  --output text

# Example output:
# trace-backend-lb-123456789.us-east-1.elb.amazonaws.com
```

**Your Backend API URL:**
```
http://trace-backend-lb-123456789.us-east-1.elb.amazonaws.com
```

#### If using ECS Service:

```bash
# Get ECS service details
aws ecs describe-services \
  --cluster trace-cluster \
  --services trace-backend-service \
  --query 'services[0].loadBalancers[0]'
```

### Frontend URL

#### Option 1: S3 Static Website

```bash
# Get S3 website URL
aws s3api get-bucket-website \
  --bucket trace-frontend-YOUR_ACCOUNT_ID

# Example output:
# http://trace-frontend-123456789012.s3-website-us-east-1.amazonaws.com
```

#### Option 2: CloudFront (Recommended)

```bash
# Get CloudFront URL
aws cloudfront list-distributions \
  --query 'DistributionList.Items[?contains(Comment, `trace`)].DomainName' \
  --output text

# Example output:
# d1abc2def3ghi.cloudfront.net
```

**Your Frontend URL:**
```
https://d1abc2def3ghi.cloudfront.net
```

### Update Frontend API URL

After you have the backend URL, update your frontend:

```bash
# Create frontend environment config
cat > frontend/.env.production << EOF
REACT_APP_API_URL=http://YOUR_BACKEND_URL_HERE
EOF

# Rebuild and redeploy frontend
docker build -t trace-frontend:latest -f Dockerfile.frontend .
docker push YOUR_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/trace-frontend:latest
```

---

## ✅ STEP 7: Test Your Deployment (5 minutes)

### 7.1 Test Backend

```bash
# Health check
curl http://YOUR_BACKEND_URL/health

# Expected response:
# {"status":"healthy","service":"excel-trace-agent","version":"2.0.0"}

# Test signup
curl -X POST http://YOUR_BACKEND_URL/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "username": "testuser",
    "password": "testpass123"
  }'
```

### 7.2 Test Frontend

```bash
# Open in browser
open http://YOUR_FRONTEND_URL

# Or
open https://YOUR_CLOUDFRONT_URL
```

You should see:
- ✅ Login page loads
- ✅ Can create account
- ✅ Can login
- ✅ Can upload files

---

## ✅ STEP 8: Set Up Auto-Deployment (Optional)

Once infrastructure is ready, every push to main will auto-deploy!

```bash
# Make a change
echo "# Update" >> README.md

# Commit and push
git add README.md
git commit -m "Test auto-deployment"
git push origin main

# Watch deployment
# Go to: https://github.com/YOUR_USERNAME/trace-excel-agent/actions
```

GitHub Actions will:
1. ✅ Run tests
2. ✅ Build Docker images
3. ✅ Push to ECR
4. ✅ Update ECS services
5. ✅ Deploy new version

---

## 📋 Quick Reference Commands

### Get Your URLs

```bash
# Backend URL
aws elbv2 describe-load-balancers \
  --query 'LoadBalancers[?contains(LoadBalancerName, `trace`)].DNSName' \
  --output text

# Frontend URL (CloudFront)
aws cloudfront list-distributions \
  --query 'DistributionList.Items[0].DomainName' \
  --output text

# Or S3 static website
aws s3 ls | grep trace-frontend
```

### View Logs

```bash
# Backend logs
aws logs tail /ecs/trace-backend --follow

# Worker logs  
aws logs tail /ecs/trace-worker --follow
```

### Check Services

```bash
# ECS services
aws ecs list-services --cluster trace-cluster

# Check service status
aws ecs describe-services \
  --cluster trace-cluster \
  --services trace-backend-service
```

### Scale Services

```bash
# Scale backend
aws ecs update-service \
  --cluster trace-cluster \
  --service trace-backend-service \
  --desired-count 5

# Scale workers
aws ecs update-service \
  --cluster trace-cluster \
  --service trace-worker-service \
  --desired-count 10
```

---

## 🎯 Your Final URLs

After completing all steps, save these:

```
Frontend: https://YOUR_CLOUDFRONT_URL
Backend:  http://YOUR_ALB_URL
         
Example:
Frontend: https://d1abc2def3ghi.cloudfront.net
Backend:  http://trace-backend-lb-123.us-east-1.elb.amazonaws.com
```

---

## ✅ Checklist

- [ ] Git repository initialized
- [ ] Files added and committed
- [ ] GitHub repository created
- [ ] Code pushed to GitHub
- [ ] JWT secret generated
- [ ] AWS credentials configured
- [ ] GitHub secrets added
- [ ] ECR repositories created
- [ ] Docker images built and pushed
- [ ] ECS cluster created
- [ ] Backend URL obtained
- [ ] Frontend URL obtained
- [ ] Backend health check passing
- [ ] Frontend accessible
- [ ] Can signup/login
- [ ] Can upload files
- [ ] Auto-deployment working

---

## 🎉 You're Done!

Your application is now deployed to AWS with:
- ✅ Auto-scaling infrastructure
- ✅ CI/CD pipeline
- ✅ Parallel processing workers
- ✅ High availability
- ✅ Monitoring and logs

**Next Steps:**
1. Add custom domain
2. Set up SSL certificate
3. Configure monitoring alarms
4. Set up backups

Need help? Check the other documentation files or open an issue!
