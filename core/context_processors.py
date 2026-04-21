def user_role(request):
    """Expose user role to all templates."""
    if request.user.is_authenticated:
        profile = getattr(request.user, "profile", None)
        role = profile.role if profile else "manager"
    else:
        role = None
    return {"user_role": role}
