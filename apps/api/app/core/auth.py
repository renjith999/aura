from typing import Annotated

from fastapi import Depends, HTTPException, status


def get_current_user_id() -> str:
    """Return the authenticated user's ID; wired to the auth story later."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


CurrentUserId = Annotated[str, Depends(get_current_user_id)]
