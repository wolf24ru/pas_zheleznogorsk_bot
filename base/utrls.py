from django.urls import re_path
from django.conf import settings

from .views import (start, UserViewSet, some_debug_func,
                    SnilsViewSet, SubscriptionsViewSet, PassPersonViewSet)

urlpatterns = [
    re_path('start', start, name='start'),
    re_path('main_menu', start, name='start'),
    re_path('us/', UserViewSet, name='UserViewSet'),
    re_path('snils/', SnilsViewSet, name='SnilsViewSet'),
    re_path('fav/', SubscriptionsViewSet, name='SubscriptionsViewSet'),
    re_path('pas/', PassPersonViewSet, name='PassPersonViewSet')
]


if settings.DEBUG:
    urlpatterns += [
        re_path('some_debug_func', some_debug_func, name='some_debug_func'),
    ]
