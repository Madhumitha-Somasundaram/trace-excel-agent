"""
OAuth integration for Google, GitHub, etc.
"""
from typing import Optional, Dict
import httpx
from fastapi import HTTPException, status
from datetime import datetime
import boto3
from models.user import User, UserResponse
from auth.security import create_access_token, create_refresh_token


# OAuth Configuration - Load from environment variables
import os

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:3000/auth/github/callback")


# DynamoDB
ddb = boto3.resource("dynamodb", region_name="us-east-1")
users_table = ddb.Table("users")


async def verify_google_token(token: str) -> Dict:
    """
    Verify Google OAuth token and get user info.

    Args:
        token: Google OAuth token

    Returns:
        Dictionary containing user information from Google

    Raises:
        HTTPException: If token verification fails
    """
    async with httpx.AsyncClient() as client:
        try:
            # Verify token with Google
            response = await client.get(
                "https://oauth2.googleapis.com/tokeninfo",
                params={"id_token": token}
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Google token"
                )

            return response.json()

        except httpx.HTTPError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not verify Google token"
            )


async def get_or_create_oauth_user(
    email: str,
    oauth_provider: str,
    oauth_id: str,
    full_name: Optional[str] = None,
    profile_picture: Optional[str] = None
) -> tuple[User, bool]:
    """
    Get existing OAuth user or create a new one.

    Args:
        email: User email
        oauth_provider: OAuth provider name ('google', 'github')
        oauth_id: User ID from OAuth provider
        full_name: User's full name
        profile_picture: URL to user's profile picture

    Returns:
        Tuple of (User object, is_new_user boolean)
    """
    try:
        # Try to find existing user by email
        response = users_table.scan(
            FilterExpression="email = :email",
            ExpressionAttributeValues={":email": email}
        )

        if response['Items']:
            # User exists, update OAuth info if needed
            user_data = response['Items'][0]
            user = User(**user_data)

            # Update OAuth info
            users_table.update_item(
                Key={"username": user.username},
                UpdateExpression="SET oauth_provider = :provider, oauth_id = :oauth_id, last_login = :login, profile_picture = :pic",
                ExpressionAttributeValues={
                    ":provider": oauth_provider,
                    ":oauth_id": oauth_id,
                    ":login": datetime.utcnow().isoformat(),
                    ":pic": profile_picture or user.profile_picture
                }
            )

            return user, False

        else:
            # Create new user (username is user_id, generate from email)
            username = email.split('@')[0]

            # Check if username already exists
            check = users_table.get_item(Key={"username": username})
            if 'Item' in check:
                # Append random suffix if username taken
                import random
                username = f"{username}{random.randint(100, 999)}"

            user = User(
                username=username,
                email=email,
                full_name=full_name,
                oauth_provider=oauth_provider,
                oauth_id=oauth_id,
                is_verified=True,
                profile_picture=profile_picture,
                last_login=datetime.utcnow().isoformat()
            )

            # Save to DynamoDB
            users_table.put_item(Item=user.dict())

            return user, True

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing OAuth user: {str(e)}"
        )


async def handle_google_oauth(code: str) -> Dict:
    """
    Handle Google OAuth callback.

    Args:
        code: Authorization code from Google

    Returns:
        Dictionary containing access token and user info
    """
    async with httpx.AsyncClient() as client:
        # Exchange code for token
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code"
            }
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to exchange code for token"
            )

        tokens = token_response.json()
        id_token = tokens.get("id_token")

        # Get user info
        user_info = await verify_google_token(id_token)

        # Get or create user
        user, is_new = await get_or_create_oauth_user(
            email=user_info["email"],
            oauth_provider="google",
            oauth_id=user_info["sub"],
            full_name=user_info.get("name"),
            profile_picture=user_info.get("picture")
        )

        # Generate JWT tokens
        access_token = create_access_token({"username": user.username, "email": user.email})
        refresh_token = create_refresh_token({"username": user.username})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": UserResponse(
                username=user.username,
                email=user.email,
                full_name=user.full_name,
                profile_picture=user.profile_picture,
                created_at=user.created_at
            ),
            "is_new_user": is_new
        }


def get_google_auth_url() -> str:
    """
    Generate Google OAuth authorization URL.

    Returns:
        Google OAuth URL for user to authorize
    """
    scopes = ["openid", "email", "profile"]

    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={GOOGLE_REDIRECT_URI}&"
        f"response_type=code&"
        f"scope={' '.join(scopes)}&"
        f"access_type=offline"
    )

    return url
