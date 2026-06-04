"""
Authentication endpoints for user signup, login, and OAuth.
"""
from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
import boto3
from models.user import User, UserCreate, UserLogin, Token, UserResponse
from auth.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    verify_refresh_token
)
from auth.oauth import handle_google_oauth, get_google_auth_url
from auth.dependencies import get_current_user
from pydantic import BaseModel


router = APIRouter(prefix="/auth", tags=["Authentication"])

# DynamoDB
ddb = boto3.resource("dynamodb", region_name="us-east-1")
users_table = ddb.Table("users")


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class GoogleAuthRequest(BaseModel):
    code: str


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate):
    """
    Register a new user with email and password.

    **Steps:**
    1. Check if email already exists
    2. Validate password strength
    3. Hash password
    4. Create user in database
    5. Return JWT tokens
    """
    try:
        # Check if email already exists
        response = users_table.scan(
            FilterExpression="email = :email",
            ExpressionAttributeValues={":email": user_data.email}
        )

        if response['Items']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )

        # Check if username already exists
        response = users_table.scan(
            FilterExpression="username = :username",
            ExpressionAttributeValues={":username": user_data.username}
        )

        if response['Items']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

        # Validate password strength
        if len(user_data.password) < 8:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 8 characters long"
            )

        if len(user_data.password) > 72:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be less than 72 characters long"
            )

        # Create user (username is the user_id)
        user = User(
            username=user_data.username,
            email=user_data.email,
            password_hash=hash_password(user_data.password),
            full_name=user_data.full_name,
            is_verified=False,
            created_at=datetime.utcnow().isoformat(),
            updated_at=datetime.utcnow().isoformat()
        )

        # Save to DynamoDB
        users_table.put_item(Item=user.dict())

        # Generate tokens
        access_token = create_access_token({"username": user.username, "email": user.email})
        refresh_token = create_refresh_token({"username": user.username})

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                profile_picture=user.profile_picture,
                created_at=user.created_at
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating user: {str(e)}"
        )


@router.post("/login", response_model=Token)
async def login(credentials: UserLogin):
    """
    Login with email and password.

    **Returns:**
    - Access token (1 hour expiry)
    - Refresh token (7 days expiry)
    - User information
    """
    try:
        # Find user by email
        response = users_table.scan(
            FilterExpression="email = :email",
            ExpressionAttributeValues={":email": credentials.email}
        )

        if not response['Items']:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        user_data = response['Items'][0]
        user = User(**user_data)

        # Check if user used OAuth
        if user.oauth_provider:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This account uses {user.oauth_provider} login. Please sign in with {user.oauth_provider}."
            )

        # Verify password
        if not user.password_hash or not verify_password(credentials.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password"
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive. Please contact support."
            )

        # Update last login
        users_table.update_item(
            Key={"username": user.username},
            UpdateExpression="SET last_login = :login",
            ExpressionAttributeValues={":login": datetime.utcnow().isoformat()}
        )

        # Generate tokens
        access_token = create_access_token({"username": user.username, "email": user.email})
        refresh_token = create_refresh_token({"username": user.username})

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse(
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                profile_picture=user.profile_picture,
                created_at=user.created_at
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during login: {str(e)}"
        )


@router.post("/refresh", response_model=Token)
async def refresh_access_token(request: RefreshTokenRequest):
    """
    Get a new access token using a refresh token.

    **Use this when your access token expires (after 1 hour).**
    """
    try:
        # Verify refresh token
        payload = verify_refresh_token(request.refresh_token)
        username = payload.get("username")

        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )

        # Get user
        response = users_table.get_item(Key={"username": username})

        if 'Item' not in response:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        user = User(**response['Item'])

        # Generate new tokens
        access_token = create_access_token({"username": user.username, "email": user.email})
        new_refresh_token = create_refresh_token({"username": user.username})

        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            user=UserResponse(
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                profile_picture=user.profile_picture,
                created_at=user.created_at
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing token: {str(e)}"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """
    Get current authenticated user information.

    **Requires authentication token in header:**
    ```
    Authorization: Bearer <your-access-token>
    ```
    """
    return UserResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        profile_picture=current_user.profile_picture,
        created_at=current_user.created_at
    )


# OAuth Endpoints

@router.get("/google/url")
async def get_google_oauth_url():
    """
    Get Google OAuth authorization URL.

    **Frontend should redirect user to this URL to start OAuth flow.**
    """
    return {"url": get_google_auth_url()}


@router.post("/google/callback", response_model=Token)
async def google_oauth_callback(request: GoogleAuthRequest):
    """
    Handle Google OAuth callback.

    **This endpoint receives the authorization code from Google
    and exchanges it for user information and JWT tokens.**
    """
    try:
        result = await handle_google_oauth(request.code)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth error: {str(e)}"
        )


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """
    Logout current user.

    **Note:** With JWT tokens, logout is handled client-side by deleting tokens.
    This endpoint is here for logging purposes and future session management.
    """
    return {
        "message": "Logged out successfully",
        "username": current_user.username
    }
