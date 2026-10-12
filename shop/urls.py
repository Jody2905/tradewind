from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
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
    path("accounts/signup/", views.signup, name="signup"),
    path("accounts/login/", auth_views.LoginView.as_view(authentication_form=EmailLoginForm,
                                                         redirect_authenticated_user=True), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
]
