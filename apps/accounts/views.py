from __future__ import annotations

from django.contrib.auth import logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .services import user_has_role

OPERATOR_ROLE_CODES = ("super_admin", "admin", "manager")


def _default_redirect_url(*, user_id: int | None) -> str:
    if user_id is not None and user_has_role(user_id, OPERATOR_ROLE_CODES):
        return reverse("operator:dashboard")
    return reverse("curriculum:learner_dashboard")


class ChalkboardLoginView(LoginView):
    authentication_form = AuthenticationForm
    template_name = "accounts/login.html"

    def get_form(self, form_class=None):  # type: ignore[override]
        form = super().get_form(form_class)
        form.fields["username"].label = "Email"
        form.fields["password"].label = "Пароль"
        form.fields["username"].widget.attrs.update(
            {
                "class": "auth-form-input",
                "placeholder": "Введите email",
                "autocomplete": "username",
                "autocapitalize": "none",
                "autofocus": True,
            }
        )
        form.fields["password"].widget.attrs.update(
            {
                "class": "auth-form-input",
                "placeholder": "Введите пароль",
                "autocomplete": "current-password",
            }
        )
        return form

    def form_valid(self, form):  # type: ignore[override]
        response = super().form_valid(form)
        if self.request.POST.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * 30)
        else:
            self.request.session.set_expiry(0)
        return response

    def get_success_url(self) -> str:
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        return _default_redirect_url(user_id=self.request.user.id)


@require_http_methods(["GET", "POST"])
def logout_view(request: HttpRequest) -> HttpResponseRedirect:
    logout(request)
    return redirect("/login/")
