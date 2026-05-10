from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("monitoring/", include("db_monitor.urls")),
    path("", include("shop.urls")),
]
