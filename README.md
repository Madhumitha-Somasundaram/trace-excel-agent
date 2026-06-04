# 🚀 Excel Trace Agent - Scalable Agentic Chat System

A production-ready, scalable agentic system for processing millions of rows and 100+ column Excel files in AWS. Features intelligent template detection, semantic column clustering, and natural language transformations.

## 🌟 Features

### Core Capabilities
- ✅ **Massive Scale**: Process Excel files with millions of rows and 100+ columns
- ✅ **AWS Native**: Built on S3, Lambda, SQS, DynamoDB, Glue, and Bedrock
- ✅ **Intelligent Templates**: Auto-detect templates (Transportation, Employee, Finance, etc.)
- ✅ **Semantic Clustering**: Group similar columns using embeddings + LLM
- ✅ **Natural Language Transformations**: Convert units, filter, aggregate via chat
- ✅ **Real-time Updates**: WebSocket support for live processing status
- ✅ **Downloadable Templates**: Generate Excel templates for each detected pattern
- ✅ **Data Quality Analysis**: Automatic profiling and issue detection

### Supported Transformations
- **Unit Conversions**: meters↔km, kg↔lbs, celsius↔fahrenheit
- **Filtering**: By status, thresholds, conditions
- **Aggregations**: Average, sum, count by groups
- **Data Cleaning**: Remove duplicates, fill nulls, standardize text
- **Date Operations**: Extract year/month/day, date math
- **Statistical**: Rankings, moving averages, percentages

## 🏗️ Architecture

```
┌─────────────┐
│   Frontend  │  React + Chat UI
│  (React)    │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   FastAPI   │  REST API + WebSocket
│   Backend   │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│     S3      │  Excel Storage
│   SQS       │  Job Queue
│  DynamoDB   │  Job State
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Lambda    │  SQS Worker (Orchestrator)
│   Worker    │
└──────┬──────┘
       │
       ↓
┌─────────────┐
│  LangGraph  │  Agent Pipeline:
│   Agent     │  1. Loader (Glue Job)
└──────┬──────┘  2. Schema Detection
       │         3. Column Clustering
       ↓         4. Template Generation
┌─────────────┐  5. Finalization
│  AWS Glue   │
│  PySpark    │  Process millions of rows
└──────┬──────┘
       │
       ↓
┌─────────────┐
│   Bedrock   │  Claude for reasoning
│   Claude    │  (template detection, code gen)
└─────────────┘
```

## 📦 Project Structure

```
Trace/
├── backend/
│   ├── app/
│   │   └── main.py                    # FastAPI endpoints
│   ├── agent_runtime/
│   │   ├── graph.py                   # LangGraph agent
│   │   ├── state.py                   # Agent state definition
│   │   └── nodes/
│   │       ├── loader_node.py         # Glue job trigger
│   │       ├── schema_node.py         # Schema detection
│   │       ├── cluster_node.py        # Column clustering
│   │       ├── template_node.py       # Template generation
│   │       ├── glue_executor_node.py  # User transformations
│   │       ├── finalize_node.py       # Results preparation
│   │       └── transformation_matcher.py
│   ├── glue_jobs/
│   │   ├── excel_processor.py         # Main Glue job
│   │   └── transformation_examples.py # PySpark patterns
│   ├── lambda/
│   │   └── sqs_worker.py              # Lambda SQS handler
│   └── tools/
│       ├── llm.py                     # Bedrock integration
│       └── s3_tool.py                 # S3 utilities
├── frontend/
│   └── src/
│       └── components/
│           └── Chat/
│               ├── ChatInterface.jsx  # Chat UI
│               └── ChatInterface.css
├── infrastructure/
│   └── cloudformation-template.yaml   # AWS CloudFormation
└── README.md
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- AWS Account with:
  - S3, Lambda, SQS, DynamoDB, Glue, Bedrock access
  - AWS CLI configured

### 1. Deploy Infrastructure

```bash
# Deploy CloudFormation stack
aws cloudformation create-stack \
  --stack-name excel-trace-agent \
  --template-body file://infrastructure/cloudformation-template.yaml \
  --capabilities CAPABILITY_NAMED_IAM

# Wait for completion
aws cloudformation wait stack-create-complete \
  --stack-name excel-trace-agent

# Get outputs
aws cloudformation describe-stacks \
  --stack-name excel-trace-agent \
  --query 'Stacks[0].Outputs'
```

### 2. Upload Glue Scripts

```bash
# Get bucket name from CloudFormation outputs
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name excel-trace-agent \
  --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue' \
  --output text)

# Upload Glue job scripts
aws s3 cp backend/glue_jobs/excel_processor.py \
  s3://$BUCKET/glue-scripts/

aws s3 cp backend/glue_jobs/transformation_examples.py \
  s3://$BUCKET/glue-scripts/
```

### 3. Deploy Worker (Choose ONE)

#### Option A: EC2 Worker (Recommended ⭐)

**Best for**: Large dependencies, long-running jobs, no size/timeout limits

```bash
cd backend

# Package for EC2
./package_for_ec2.sh

# Upload to EC2
scp -i your-key.pem ec2-deployment.tar.gz ec2-user@<EC2-IP>:~/

# On EC2: Deploy
tar -xzf ec2-deployment.tar.gz
cd ec2_package
sudo ./deploy_ec2.sh

# Start the worker
sudo systemctl start excel-trace-worker
sudo systemctl enable excel-trace-worker
```

📖 **Full EC2 Setup Guide**: See `backend/EC2_DEPLOYMENT.md`

#### Option B: Lambda Function

**Best for**: Sporadic traffic, simpler setup (has size/timeout limitations)

```bash
cd backend

# Build Lambda layers
./build_lambda_layer.sh

# Deploy (follow prompts)
```

**Note**: Lambda has 250MB size limit and 15-minute timeout. For this workload with large dependencies (pandas, sklearn, transformers), EC2 is strongly recommended.

### 4. Start Backend

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AWS_REGION=us-east-1
export BUCKET_NAME=excel-trace-agent-bucket-<account-id>
export QUEUE_URL=https://sqs.us-east-1.amazonaws.com/549955691461/excel-trace-queue

# Run API
uvicorn app.main:app --reload --port 8000
```

### 5. Start Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm start
```

Visit http://localhost:3000 to use the application!

## 📖 Usage

### 1. Upload Excel File

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@your_data.xlsx"

# Response:
{
  "job_id": "abc-123-def",
  "message": "File uploaded and queued successfully"
}
```

### 2. Check Job Status

```bash
curl http://localhost:8000/job/{job_id}

# Response:
{
  "job_id": "abc-123-def",
  "status": "COMPLETED",
  "progress": 100,
  "current_step": "processing_complete"
}
```

### 3. Chat with Agent

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "abc-123-def",
    "message": "Convert distance from meters to kilometers"
  }'
```

### 4. Download Templates

```bash
curl http://localhost:8000/templates/{job_id}

# Response:
{
  "templates": [
    {
      "name": "Transportation_template.xlsx",
      "type": "transportation",
      "url": "https://s3.../presigned-url"
    }
  ]
}
```

## 💬 Example Chat Interactions

### Template Discovery
```
User: What templates did you find?
Agent: I detected 3 templates:
       1. Transportation (vehicle_id, route, distance, fuel_consumption)
       2. Employee (employee_id, name, department, salary)
       3. Finance (transaction_id, amount, date, account)
       
       Click below to download each template!
```

### Unit Conversion
```
User: Convert distance from meters to kilometers
Agent: I'll convert the 'distance_m' column to kilometers. 
       This will create a new column 'distance_km'.
       Should I proceed?
       
User: Yes
Agent: ✅ Transformation queued! Processing 2.5M rows...
       I'll update you when it's done.
```

### Aggregation
```
User: Calculate average salary by department
Agent: I'll group by 'department' and calculate:
       - Average salary
       - Min/Max salary
       - Employee count
       
       Ready to execute?
```

### Data Quality
```
User: Show me data quality issues
Agent: Found 3 issues:
       1. ⚠️ 'phone_number' has 45% null values
       2. ℹ️ 'status' column has no variance (all 'active')
       3. ⚠️ 12,450 duplicate rows detected
```

## 🔧 Configuration

### Environment Variables

```bash
# AWS Configuration
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-key>
AWS_SECRET_ACCESS_KEY=<your-secret>

# Service Configuration
BUCKET_NAME=excel-trace-agent-bucket-<account-id>
QUEUE_URL=https://sqs.us-east-1.amazonaws.com/.../excel-trace-queue
JOBS_TABLE=jobs

# Bedrock Model
MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
```

### Glue Job Configuration

Modify `infrastructure/cloudformation-template.yaml`:

```yaml
NumberOfWorkers: 10          # Scale based on file size
WorkerType: G.1X             # G.1X, G.2X, or G.4X
MaxRetries: 2                # Retry failed jobs
Timeout: 2880                # 48 hours max
```

## 📊 Performance

### Benchmarks
- **2M rows, 50 columns**: ~5 minutes (10 G.1X workers)
- **10M rows, 100 columns**: ~15 minutes (20 G.2X workers)
- **50M rows, 150 columns**: ~45 minutes (50 G.2X workers)

### Cost Optimization
- Use **Parquet** for intermediate storage (10x compression)
- Enable **Glue job bookmarks** for incremental processing
- Use **S3 Lifecycle policies** to archive old files
- Set **DynamoDB to on-demand** for variable workloads

## 🛡️ Security

- ✅ S3 bucket encryption at rest (SSE-S3)
- ✅ IAM roles with least privilege
- ✅ VPC endpoints for private AWS service access
- ✅ CloudWatch logging enabled
- ✅ DynamoDB point-in-time recovery
- ✅ Presigned URLs for template downloads (1-hour expiry)

## 🐛 Troubleshooting

### Issue: Glue job times out
**Solution**: Increase `NumberOfWorkers` or `Timeout` in CloudFormation

### Issue: Lambda function fails
**Solution**: Check CloudWatch logs for Lambda and increase memory if needed

### Issue: Template detection is incorrect
**Solution**: Refine the prompt in `tools/llm.py` → `analyze_columns_for_template()`

### Issue: Transformation fails
**Solution**: Check Glue job logs in CloudWatch, verify column names match

## 📈 Monitoring

### CloudWatch Dashboards

Key metrics to monitor:
- Lambda invocations and errors
- SQS queue depth
- Glue job duration and failures
- DynamoDB read/write capacity
- S3 request rate

### Alarms

Configured alarms:
- High Lambda error rate (>10 errors in 5 min)
- Messages in DLQ (any)
- Glue job failures

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- **LangGraph** for agent orchestration
- **AWS Bedrock** for Claude AI integration
- **Sentence Transformers** for semantic embeddings
- **Apache Spark** for big data processing

## 📞 Support

- 📧 Email: support@example.com
- 💬 Slack: [Join our community](https://slack.example.com)
- 🐛 Issues: [GitHub Issues](https://github.com/yourorg/trace/issues)

---

**Built with ❤️ for data teams who work with massive Excel files**
