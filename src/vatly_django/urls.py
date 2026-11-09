from django.urls import path

from . import views

app_name = "vatly_django"
urlpatterns = [
    path("checkout/<slug:offer>/", views.checkout, name="checkout"),
    path("portal/", views.portal, name="portal"),
    path("webhook/", views.webhook, name="webhook"),
]
