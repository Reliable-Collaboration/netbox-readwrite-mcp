from django.urls import path
from .views import FilterSchemaView, RootView
from .dashboard import DashboardView, DashboardWidgetSchemaView
from .configuration import (
    ConfigurationSchemaView,
    RevisionCollectionView,
    RevisionDetailView,
    RevisionActivateView,
)

urlpatterns = [
    path("self/dashboard/", DashboardView.as_view(), name="self-dashboard"),
    path("dashboard-widgets/", DashboardWidgetSchemaView.as_view(), name="dashboard-widgets"),
    path("", RootView.as_view(), name="api-root"),
    path("filter-schema/", FilterSchemaView.as_view(), name="filter-schema"),
    path("configuration-schema/", ConfigurationSchemaView.as_view(), name="configuration-schema"),
    path("config-revisions/", RevisionCollectionView.as_view(), name="config-revisions"),
    path("config-revisions/<int:pk>/", RevisionDetailView.as_view(), name="config-revision"),
    path(
        "config-revisions/<int:pk>/activate/", RevisionActivateView.as_view(), name="config-revision-activate"
    ),
]
