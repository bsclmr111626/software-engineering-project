from .permissions import can_manage_scenarios, can_run_simulations, get_role, is_admin, registration_open


def role(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"registration_open": registration_open()}
    return {
        "current_role": get_role(user),
        "user_is_admin": is_admin(user),
        "user_can_manage": can_manage_scenarios(user),
        "user_can_simulate": can_run_simulations(user),
    }
