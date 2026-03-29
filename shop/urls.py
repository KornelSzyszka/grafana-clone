from django.urls import path

from . import views

app_name = "shop"

urlpatterns = [
    path("", views.api_root, name="root"),
    path("api/products/", views.product_list_view, name="product-list"),
    path("api/products/<slug:slug>/", views.product_detail_view, name="product-detail"),
    path("api/users/<int:user_id>/orders/", views.order_history_view, name="order-history"),
    path("api/reports/sales/", views.sales_report_view, name="sales-report"),
]
