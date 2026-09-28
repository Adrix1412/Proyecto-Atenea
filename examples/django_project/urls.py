from django.urls import include, path

urlpatterns = [path("api/alicia/", include("alicia_core.django_app.urls"))]
