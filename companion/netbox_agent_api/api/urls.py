from django.urls import path
from .views import FilterSchemaView, RootView
from .imports import ImportCatalogView, ImportView
from .rename import RenameCatalogView, RenameView
from .bulk_edit import BulkEditCatalogView, BulkEditAPIView
from .patterns import PatternCatalogView, PatternView
from .dashboard import DashboardView, DashboardWidgetSchemaView
from .configuration import (
    ConfigurationSchemaView,
    RevisionCollectionView,
    RevisionDetailView,
    RevisionActivateView,
)

urlpatterns = [
    path("pattern-create/", PatternCatalogView.as_view(), name="pattern-create"),
    path("pattern-create/<str:model>/", PatternView.as_view(), name="pattern-create-model"),
    path("bulk-edit/", BulkEditCatalogView.as_view(), name="bulk-edit"),
    path("bulk-edit/<str:model>/", BulkEditAPIView.as_view(), name="bulk-edit-model"),
    path("bulk-rename/", RenameCatalogView.as_view(), name="bulk-rename"),
    path("bulk-rename/<str:model>/", RenameView.as_view(), name="bulk-rename-model"),
    path("imports/", ImportCatalogView.as_view(), name="imports"),
    path("imports/<str:model>/", ImportView.as_view(), name="import-model"),
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
