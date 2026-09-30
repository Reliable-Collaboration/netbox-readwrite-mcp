from django.urls import path
from .views import FilterSchemaView, RootView

urlpatterns = [
    path("", RootView.as_view(), name="api-root"),
    path("filter-schema/", FilterSchemaView.as_view(), name="filter-schema"),
]
