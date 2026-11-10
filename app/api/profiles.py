from typing import List, Optional
from fastapi import APIRouter, HTTPException, status, Query, Depends, Response

from app.schemas import (
    ProfileResponse,
    ProfileCreate,
    ProfileUpdate,
    ProfileImpactResponse,
    ProfileDeleteRequest
)
from app.core.profiles import (
    list_profiles,
    get_profile,
    get_active_profile_id,
    set_active_profile_id,
    create_profile,
    update_profile,
    get_profile_impact,
    delete_profile
)

router = APIRouter(prefix="/profiles")

@router.get("", response_model=List[ProfileResponse])
def get_profiles_endpoint(include_archived: bool = Query(True, description="Whether to include archived profiles")):
    """Lists all registered profiles, indicating which is currently active."""
    profiles = list_profiles(include_archived=include_archived)
    return [ProfileResponse(**p.to_dict()) for p in profiles]

@router.get("/active", response_model=ProfileResponse)
def get_active_profile_endpoint():
    """Retrieves the currently selected active profile."""
    active_id = get_active_profile_id()
    profile = get_profile(active_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active profile '{active_id}' not found."
        )
    return ProfileResponse(**profile.to_dict())

@router.post("", response_model=ProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile_endpoint(payload: ProfileCreate):
    """Creates a new isolated financial profile workspace with its own database and storage."""
    try:
        profile = create_profile(payload.name)
        return ProfileResponse(**profile.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create profile: {str(e)}"
        )

@router.post("/{profile_id}/select", response_model=ProfileResponse)
def select_profile_endpoint(profile_id: str):
    """Sets the active profile for the application."""
    try:
        profile = set_active_profile_id(profile_id)
        return ProfileResponse(**profile.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.patch("/{profile_id}", response_model=ProfileResponse)
def update_profile_endpoint(profile_id: str, payload: ProfileUpdate):
    """Updates profile name or archive state with safeguards."""
    try:
        profile = update_profile(
            profile_id=profile_id,
            name=payload.name,
            is_archived=payload.is_archived
        )
        return ProfileResponse(**profile.to_dict())
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/{profile_id}/impact", response_model=ProfileImpactResponse)
def get_profile_impact_endpoint(profile_id: str):
    """Calculates impact metrics before permanent profile deletion."""
    try:
        impact = get_profile_impact(profile_id)
        return ProfileImpactResponse(**impact)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile_endpoint(profile_id: str, payload: ProfileDeleteRequest):
    """
    Permanently deletes a profile and its dedicated storage directory.
    Requires exact name confirmation.
    """
    try:
        delete_profile(profile_id=profile_id, confirm_name=payload.confirm_name)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete profile: {str(e)}"
        )

