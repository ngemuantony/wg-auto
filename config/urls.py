"""
URL configuration for config project.

"""
from django.contrib import admin
from django.urls import path, include
from config import settings

urlpatterns = [
    path('grappelli/', include('grappelli.urls')),
    path('admin/', admin.site.urls),
    path('', include('wireguard.urls'))
]
