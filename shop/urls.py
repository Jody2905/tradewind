from django.contrib.auth import views as auth_views
from django.urls import path

from . import staff, views
from .forms import EmailLoginForm

urlpatterns = [
    path("", views.catalogue, name="catalogue"),
    path("p/<slug:slug>/", views.product_detail, name="product"),
    path("basket/", views.basket_view, name="basket"),
    path("basket/add/<int:product_id>/", views.basket_add, name="basket_add"),
    path("basket/update/", views.basket_update, name="basket_update"),
    path("basket/discount/", views.basket_discount, name="basket_discount"),
    path("checkout/", views.checkout, name="checkout"),
    path("orders/", views.my_orders, name="my_orders"),
    path("orders/<str:number>/", views.order_detail, name="order"),
    path("orders/<str:number>/cancel/", views.order_cancel, name="order_cancel"),
    # Staff
    path("staff/", staff.dashboard, name="staff_dashboard"),
    path("staff/orders/", staff.order_list, name="staff_orders"),
    path("staff/orders/expire/", staff.expire_now, name="staff_expire"),
    path("staff/orders/<str:number>/", staff.order_detail, name="staff_order"),
    path("staff/orders/<str:number>/slip/", staff.packing_slip, name="staff_slip"),
    path("staff/orders/<str:number>/<str:action>/", staff.order_action, name="staff_order_action"),
    path("staff/stock/", staff.stock, name="staff_stock"),
    path("staff/stock/<str:sku>/", staff.stock_history, name="staff_stock_history"),
    path("staff/stock/<str:sku>/<str:action>/", staff.stock_action, name="staff_stock_action"),
    path("staff/sales/", staff.sales, name="staff_sales"),
    path("staff/sales.xlsx", staff.sales_xlsx, name="staff_sales_xlsx"),
    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/login/", auth_views.LoginView.as_view(authentication_form=EmailLoginForm,
                                                         redirect_authenticated_user=True), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]
