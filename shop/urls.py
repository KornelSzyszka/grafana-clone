from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.api_root, name="root"),
    path("products/", views.products_page, name="products-page"),
    path("users/", views.users_page, name="users-page"),
    path("reports/sales/", views.sales_report_page, name="sales-report-page"),
    path("api/products/", views.product_list_view, name="product-list"),
    path("api/products/<slug:slug>/", views.product_detail_view, name="product-detail"),
    path("api/users/", views.users_api, name="users"),
    path("api/users/<int:user_id>/orders/", views.order_history_view, name="order-history"),
    path("api/reports/sales/", views.sales_report_api, name="sales-report"),
]
