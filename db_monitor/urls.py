from django.urls import path

from db_monitor import views

app_name = "db_monitor"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("compare/", views.compare_view, name="compare"),
    path("snapshots/<int:snapshot_id>/", views.snapshot_overview, name="snapshot-overview"),
    path("snapshots/<int:snapshot_id>/<slug:section>/", views.snapshot_section, name="snapshot-section"),
]
