from django.urls import path
from .views import FilterSchemaView, RootView
from .imports import ImportCatalogView, ImportView
from .rename import RenameCatalogView, RenameView
from .bulk_edit import BulkEditCatalogView, BulkEditAPIView
from .patterns import PatternCatalogView, PatternView
from .account import ProfileView, PreferencesView, PasswordView, NotificationsView
from .utilities import SearchView, MarkdownView
from .administration import SystemView, DatabaseSchemaView, QueueTasksView
from .media import MediaCatalogView, MediaView
from .batch_actions import DisconnectCatalogView, DisconnectView, SyncCatalogView, SyncView
from .scripts import ScriptCatalogView, ScriptSchemaView, ScriptSourceView
from .chassis import ChassisCatalogView, ChassisMembersView
from .deletion import DeleteCatalogView, DeleteView
from .exports import ExportCatalogView, ExportView
from .dashboard import DashboardView, DashboardWidgetSchemaView
from .configuration import (
    ConfigurationSchemaView,
    RevisionCollectionView,
    RevisionDetailView,
    RevisionActivateView,
)

urlpatterns = [
    path("scripts/", ScriptCatalogView.as_view(), name="scripts"),
    path("scripts/<int:pk>/", ScriptSchemaView.as_view(), name="script-schema"),
    path("scripts/<int:pk>/source/", ScriptSourceView.as_view(), name="script-source"),
    path("virtual-chassis/", ChassisCatalogView.as_view(), name="chassis"),
    path("virtual-chassis/<int:pk>/members/", ChassisMembersView.as_view(), name="chassis-members"),
    path("native-delete/", DeleteCatalogView.as_view(), name="native-delete"),
    path("native-delete/<str:model>/", DeleteView.as_view(), name="native-delete-model"),
    path("self/notifications/", NotificationsView.as_view(), name="self-notifications"),
    path("exports/", ExportCatalogView.as_view(), name="exports"),
    path("exports/<str:model>/", ExportView.as_view(), name="export-model"),
    path("bulk-disconnect/", DisconnectCatalogView.as_view(), name="bulk-disconnect"),
    path("bulk-disconnect/<str:model>/", DisconnectView.as_view(), name="bulk-disconnect-model"),
    path("bulk-sync/", SyncCatalogView.as_view(), name="bulk-sync"),
    path("bulk-sync/<str:model>/", SyncView.as_view(), name="bulk-sync-model"),
    path("media/", MediaCatalogView.as_view(), name="media"),
    path("media/<str:model>/<int:pk>/<str:field>/", MediaView.as_view(), name="media-content"),
    path("self/profile/", ProfileView.as_view(), name="self-profile"),
    path("self/preferences/", PreferencesView.as_view(), name="self-preferences"),
    path("self/password/", PasswordView.as_view(), name="self-password"),
    path("search/", SearchView.as_view(), name="search"),
    path("render-markdown/", MarkdownView.as_view(), name="render-markdown"),
    path("system/", SystemView.as_view(), name="system"),
    path("database-schema/", DatabaseSchemaView.as_view(), name="database-schema"),
    path("queue-tasks/", QueueTasksView.as_view(), name="queue-tasks"),
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
