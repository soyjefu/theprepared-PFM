from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('account.urls')), # 루트 경로를 account 앱으로
    path('admin/', admin.site.urls),
]