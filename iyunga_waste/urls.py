from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from bins.views import IoTDataReceiveView, BinStatusView, BinMapDataView, get_full_bins, seed_data, CollectorBinsView, HouseholdBinsView, mark_bin_collected, report_bin_issue
from accounts.views import (
    login_view, logout_view, dashboard, RegisterView, HouseholdListView, HouseholdDetailView, 
    payments_page, reports_page, profile_page, household_page, register_bin, edit_bin,
    AdminStatsView, CollectorStatsView, HouseholdStatsView, UserListView,
    admin_users, admin_bins, admin_households, admin_payments, admin_payment_recipients, admin_routes,
    collector_schedules, household_schedules, admin_schedules, collector_bins
)
from payments.views import PaymentCreateView, ReceiptListView, PaymentHistoryView, calculate_fee, AllPaymentsView
from reports.views import (
    DashboardStatsView, WasteTrendsView, BinUsageStatsView, 
    PaymentSummaryView, RecyclableStatsView, optimize_route, 
    export_csv, export_pdf, optimize_collector_route,
    CollectorSchedulesView, UpdateScheduleStatusView, HouseholdSchedulesView, AdminSchedulesView
)

urlpatterns = [
    path('', login_view, name='home'),
    path('admin/', admin.site.urls),
    
    path('accounts/login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard, name='dashboard'),
    
    # Admin management pages
    path('manage/users/', admin_users, name='admin_users'),
    path('manage/bins/', admin_bins, name='admin_bins'),
    path('manage/households/', admin_households, name='admin_households'),
    path('manage/payments/', admin_payments, name='admin_payments'),
    path('manage/payments/recipients/', admin_payment_recipients, name='admin_payment_recipients'),
    path('manage/routes/', admin_routes, name='admin_routes'),
    path('manage/schedules/', admin_schedules, name='admin_schedules'),
    
    path('collector/bins/', collector_bins, name='collector_bins'),
    path('collector/schedules/', collector_schedules, name='collector_schedules'),
    path('household/schedules/', household_schedules, name='household_schedules'),
    
    path('payments/', payments_page, name='payments_page'),
    path('reports/', reports_page, name='reports_page'),
    path('profile/', profile_page, name='profile'),
    path('household/', household_page, name='household'),
    path('household/register-bin/', register_bin, name='register_bin'),
    path('household/bin/<int:bin_id>/edit/', edit_bin, name='edit_bin'),
    
    path('api/register/', RegisterView.as_view(), name='api_register'),
    path('api/iot/', IoTDataReceiveView.as_view(), name='iot_receive'),
    path('api/bins/status/', BinStatusView.as_view(), name='bin_status'),
    path('api/bins/map/', BinMapDataView.as_view(), name='bin_map'),
    path('api/bins/full/', get_full_bins, name='full_bins'),
    path('api/bins/collector/', CollectorBinsView.as_view(), name='collector_bins'),
    path('api/bins/household/', HouseholdBinsView.as_view(), name='household_bins'),
    path('api/bins/collect/', mark_bin_collected, name='bin_collect'),
    path('api/bins/report-issue/', report_bin_issue, name='report_issue'),
    path('api/seed-data/', seed_data, name='seed_data'),
    
    path('api/households/', HouseholdListView.as_view(), name='households'),
    path('api/households/<int:pk>/', HouseholdDetailView.as_view(), name='household_detail'),
    
    path('api/payments/create/', PaymentCreateView.as_view(), name='payments_create'),
    path('api/payments/history/', PaymentHistoryView.as_view(), name='payment_history'),
    path('api/payments/all/', AllPaymentsView.as_view(), name='payments_all'),
    path('api/receipts/', ReceiptListView.as_view(), name='receipts'),
    path('api/calculate-fee/', calculate_fee, name='calculate_fee'),
    
    path('api/stats/admin/', AdminStatsView.as_view(), name='admin_stats'),
    path('api/stats/collector/', CollectorStatsView.as_view(), name='collector_stats'),
    path('api/stats/household/', HouseholdStatsView.as_view(), name='household_stats'),
    path('api/stats/dashboard/', DashboardStatsView.as_view(), name='dashboard_stats'),
    path('api/stats/waste-trends/', WasteTrendsView.as_view(), name='waste_trends'),
    path('api/stats/bin-usage/', BinUsageStatsView.as_view(), name='bin_usage'),
    path('api/stats/payments/', PaymentSummaryView.as_view(), name='payment_summary'),
    path('api/stats/recyclable/', RecyclableStatsView.as_view(), name='recyclable_stats'),
    
    path('api/route/optimize/', optimize_route, name='optimize_route'),
    path('api/route/collector/', optimize_collector_route, name='optimize_collector_route'),

    path('api/schedules/collector/', CollectorSchedulesView.as_view(), name='collector_schedules_api'),
    path('api/schedules/<int:schedule_id>/status/', UpdateScheduleStatusView.as_view(), name='update_schedule_status_api'),
    path('api/schedules/household/', HouseholdSchedulesView.as_view(), name='household_schedules_api'),
    path('api/schedules/admin/', AdminSchedulesView.as_view(), name='admin_schedules_api'),
    
    path('api/users/list/', UserListView.as_view(), name='users_list'),
    
    path('reports/export/csv/', export_csv, name='export_csv'),
    path('reports/export/pdf/', export_pdf, name='export_pdf'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)