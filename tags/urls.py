from django.urls import path

from tags import views

app_name = "tags"

urlpatterns = [
    path("", views.tag_list, name="list"),
    path("<str:slug>/", views.tag_detail, name="detail"),
]
