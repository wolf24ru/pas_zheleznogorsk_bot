from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from telegram_django_bot import forms as td_forms
from base.models import SNILS, Pass_User
from telegram_django_bot.user_viewset import UserForm
from django import forms


class SNILSForm(td_forms.TelegramModelForm):
    form_name = _('SNILS')

    class Meta:
        model = SNILS
        fields = ['number', 'users_snils']

    # def _multichoice_intersection(super, set_from_user, set_from_db):
    def _multichoice_intersection(self, set_from_user, set_from_db):
        if len(set_from_db):
            db_values_type = type(next(iter(set_from_db)))
            set_from_user = set([db_values_type(elem) for elem in set_from_user])

        if set_from_db.intersection(set_from_user):
            new_pks = set_from_user
        else:
            if len(set_from_user):
                new_pks = set_from_db.union(set_from_user)
            else:
                new_pks = []
        return list(new_pks)


class SubscriptionsForm(td_forms.TelegramModelForm):
    form_name = _('Subscriptions')

    class Meta:
        model = Pass_User
        fields = ['surname', 'name', 'patronymic', 'bb_date', 'status_solution']


class PassPersonForm(td_forms.TelegramModelForm):
    form_name = _('pass')

    class Meta:
        model = Pass_User
        fields = ['surname', 'name', 'patronymic', 'bb_date', 'status_solution']
        full_show = ['surname', 'name', 'patronymic', 'bb_date', 'status_solution']


class FindPersonForm(td_forms.TelegramModelForm):
    form_name = _("find person")
    snils = forms.IntegerField()

    class Meta:
        model = Pass_User
        fields = ['snils', 'surname']


class UserFormNew(UserForm):
    class Meta:
        model = get_user_model()

        fields = ['telegram_language_code', 'date']

        labels = {
            'telegram_language_code': _("Language"),
            'date': _('Reminder')
        }
