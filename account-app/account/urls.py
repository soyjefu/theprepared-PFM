from django.urls import path
from . import views

app_name = 'account'

urlpatterns = [
    # 루트 경로: 로그인 상태에 따라 다른 페이지를 보여주는 뷰로 연결
    path('', views.index_view, name='index'), 
    
    # 인증 관련 URL
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('signup/', views.signup_view, name='signup'),
    
    # 가계부 기능 URL (접두사 없이)
    path('transaction/new/', views.transaction_create, name='transaction_create'), # 거래입력을 첫 번째로
    path('list/', views.transaction_list, name='transaction_list'),
    path('transaction/<int:pk>/update/', views.transaction_update, name='transaction_update'),
    path('transaction/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),
    path('status/', views.asset_status, name='asset_status'),
    path('budget/', views.budget_view, name='budget_view'),

    # 환경설정 페이지 URL 추가
    path('settings/', views.settings_view, name='settings'), 
    path('preset/<int:pk>/update/', views.preset_update, name='preset_update'),
    path('preset/<int:pk>/delete/', views.preset_delete, name='preset_delete'),
    path('account/<int:pk>/update/', views.account_update, name='account_update'),
    path('account/<int:pk>/delete/', views.account_delete, name='account_delete'),
    
    #예산 및 통계계 관련
    path('reports/', views.reports_view, name='reports'),
]