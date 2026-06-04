#!/bin/bash

echo "🔐 Setting up Authentication System..."
echo ""

# Backend setup
echo "📦 Installing backend dependencies..."
cd backend
pip install passlib[bcrypt] python-jose[cryptography] pyjwt httpx pydantic[email]

echo ""
echo "🗄️ Creating DynamoDB users table..."
python scripts/create_users_table.py

echo ""
echo "⚙️ Updating secret key..."
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "Generated SECRET_KEY: $SECRET_KEY"
echo "Please update backend/auth/security.py with this key!"

cd ..

# Frontend setup
echo ""
echo "📦 Installing frontend dependencies..."
cd frontend
npm install react-router-dom

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Update backend/auth/security.py with the generated SECRET_KEY"
echo "2. (Optional) Configure Google OAuth in backend/auth/oauth.py"
echo "3. Start backend: cd backend && uvicorn app.main:app --reload"
echo "4. Start frontend: cd frontend && npm start"
echo "5. Visit http://localhost:3000 and sign up!"
