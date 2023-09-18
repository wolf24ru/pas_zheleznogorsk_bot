import copy
import logging

from django.conf import settings
from django.utils.translation import (gettext as _, gettext_lazy)
from django.forms.models import ModelMultipleChoiceField

from telegram_django_bot.td_viewset import TelegramViewSet
from telegram_django_bot.user_viewset import UserViewSet as TGUserViewSet, UserForm
from telegram_django_bot.utils import handler_decor
from telegram_django_bot.telegram_lib_redefinition import InlineKeyboardButtonDJ
from telegram_django_bot.routing import telegram_reverse
from telegram_django_bot.tg_dj_bot import TG_DJ_Bot

from telegram import Update
from datetime import datetime, timedelta

from .forms import (SNILSForm, SubscriptionsForm, PassPersonForm,
                    FindPersonForm, UserFormNew)
from .models import User, SNILS, Pass_User
from .cron import _pass_downloaded, _create_user_in_db


# todo понять как сделать Русский язык по умолчанию
#  возможно это еще зависит от языка в настройках телеги


def get_or_none(model, id):
    try:
        return model.objects.get(user=id)
    except model.DoesNotExist:
        return None


@handler_decor()
def start(bot: TG_DJ_Bot, update: Update, user: User):
    message = (_(f"Hellow, %(name)s!\n") % {'name': user.first_name} + _(
        "I'm bot witch can show you status of pass in Zheleznogorsk sity "
        "and, if necessary, notify of its change.\n"
        "\n"
        "Also, i will remind you about the pass in advance so that you provide the documents.\n\n"
        "🔍 New search - to find by SNILS (Specified when submitting the application)\n\n"
        "🗃️ Favorite - favorite pass list\n") +
               "\n\nБот находится в стадии разработки: возможно не своевременное обновление базы, перебои в работе")
    # _(
    #     f'Здравствуйте, {user.first_name}!\n'
    #     f'\nЯ бот, который может показывать статус пропуска в город Железногорск,'
    #     f' и при необходимости уведомлять о его изменении.\n'
    #     '\n'
    #     f'Так же, я заранее напомню об окончании пропуска, что бы Вы своевременно подали документы.\n\n'
    #     f'🔍 Новый поиск - позволит совершить поиск по СНИЛС\n\n'
    #     f'🗃️ Избранное - избранный список пропусков\n'
    # )

    buttons = [
        [
            InlineKeyboardButtonDJ(
                text=_('🔍 New search'),
                callback_data='snils/sl'),
            InlineKeyboardButtonDJ(
                text=_('🗃️ Favorite'),
                callback_data='fav/sl')
        ],
        [InlineKeyboardButtonDJ(text=_('⚙️ Settings'), callback_data='us/se')]
    ]

    return bot.edit_or_send(update, message, buttons)


class PassPersonViewSet(TelegramViewSet):
    viewset_name = 'PassPerson'
    model_form = PassPersonForm
    queryset = Pass_User.objects.all()
    snils = None

    def create(self, field=None, value=None, initial_data=None, snils=None):
        """creating item, could be several steps"""

        if field is None and value is None:
            self.user.clear_status(commit=False)
        elif field == 'None' and value == 'None':
            self.user.clear_status(commit=False)
            field = None
            value = None
        if snils:
            initial_data = {
                'snils': snils
            }
        return self.create_or_update_helper(field, value, 'create', initial_data=initial_data)

    def create_or_update_helper(self, field, value, func_response='create', instance=None, initial_data=None):
        data = {} if initial_data is None else copy.deepcopy(initial_data)
        show_field_variants_for_update = (func_response == 'change') and (value is None) and (
                self.update.message is None)

        if (type(field) == str) and field:
            field_value = None
            if value:
                if value == self.NONE_VARIANT_SYMBOLS:
                    data[field] = None
                else:
                    field_value = value
            elif self.update.message:
                field_value = self.update.message.text

            data[field] = field_value
        else:
            self.snils = data['snils']
        form_kwargs = {
            'user': self.user,
            'data': data,
        }
        instance_id = None
        if instance:
            form_kwargs['instance'] = instance
            instance_id = instance.pk

        self.form = FindPersonForm(**form_kwargs)
        form = self.form

        if not show_field_variants_for_update and not data.get('surname'):
            form.save(is_completed=True)

        if field and form.data.get('snils'):
            # self.queryset = self.queryset.filter(surname=field.upper())
            res = self.show_list(0, 10, 1, snils=form.data['snils'], find_surname=data.get('surname').upper())
        else:
            res = self.gm_next_field(
                form.next_field,
                func_response=func_response,
                instance_id=instance_id
            )
        return res

    def get_or_create_data(self, snils, surname=None):
        snils = SNILS.objects.get(id=snils)
        all_pass = snils.pass_user.all()
        if all_pass:
            return all_pass
        else:
            new_data_list = _pass_downloaded(snils.number)
            if not new_data_list:
                return new_data_list
            for person in new_data_list:
                _create_user_in_db(person)
            return self.get_or_create_data(snils.id)

    def get_queryset(self):

        if self.snils:
            hundred_days_left = datetime.today() - timedelta(days=100)
            self.queryset = self.queryset.filter(snils_pass_s__id=self.snils).exclude(bb_date__lt=hundred_days_left).order_by("-update_date")
            return self.queryset
        else:
            return self.queryset

    def snils_error(self, snils):
        mess = _('<b>SNILS does not work</b>\nCheck the correctness of the data\n\n')
        # mess = '<b>СНИЛС не дает результата</b>\nПроверьте корректность данных\n\n'
        buttons = [[
            InlineKeyboardButtonDJ(
                text=_('🔙 Back'),
                callback_data=f'snils/se&{snils}')
        ]]
        return self.CHAT_ACTION_MESSAGE, (mess, buttons)

    def show_list(self, page=0, per_page=10, columns=1, snils=None, find_surname=None, *args, **kwargs):
        self.per_page = per_page
        self.columns = columns
        try:
            if snils:

                snils_number = SNILS.objects.get(id=snils).number
                if len(snils_number) >= 11:
                    self.snils = snils
                    self.get_queryset()
                    if find_surname:
                        self.queryset = self.queryset.filter(surname=find_surname.rstrip())
                else:
                    return self.snils_error(snils)
        except:
            assert 'error request'
        else:
            data = self.get_or_create_data(self.snils)
            if not data:
                return self.snils_error(snils)
            __, (mess, buttons) = super().show_list(int(page), int(per_page), int(columns))

            buttons += [
                [InlineKeyboardButtonDJ(
                    text=_('🔙 Back'),
                    callback_data='snils/sl')],
            ]
            if find_surname:
                if self.queryset:
                    # mess = 'Найденные варианты'
                    mess = _('Found options:')
                else:
                    mess = _('The search has not given any results. Check the correctness of the entered data\n'
                             'Or you data is not in the database.')
                        # (f'Поиск не дал результатов, проверти правильность введенных данных\n'
                        #     f'Либо ваших данных нет в базе данных.')
            else:
                mess = _('All list of pass:')
                # mess = f'Полный список пропусков:'
            return self.CHAT_ACTION_MESSAGE, (mess, buttons)

    def gm_show_list_button_names(self, it_m, model):
        return f'{model}'

    def gm_show_list_elem_info(self, model, it_m: int) -> str:
        mess = f'{model}\n' if self.use_name_and_id_in_elem_showing else f'{it_m}. '
        mess += self.gm_show_elem_or_list_fields(model)
        mess += '\n\n'
        return mess

    def show_elem(self, model_or_pk, mess=''):
        model = self.get_orm_model(model_or_pk)
        if model:
            mess += self.gm_show_elem_or_list_fields(model, is_elem=True)
            buttons = self._gm_show_elem_create_buttons(model)

            return self.CHAT_ACTION_MESSAGE, (mess, buttons)
        else:
            return self.gm_no_elem(model_or_pk)

    def retun_to_list(self, callback):
        list_callback = callback[0][0].callback_data.split('&')
        if len(list_callback) <= 2:
            return callback[1][0].callback_data
            # return 'fav/sl'
        elif len(callback[0]) == 1:
            list_callback[1] = str(int(list_callback[1]) - 1)
            retun_callback_data = '&'.join(list_callback)
            return retun_callback_data
        else:
            list_callback[1] = str(int(list_callback[1]) + 1)
            retun_callback_data = '&'.join(list_callback)
            return retun_callback_data
    def _gm_show_elem_create_buttons(self, model, elem_per_raw=2):
        buttons = []
        if 'show_list' in self.actions:
            if self.user.subscriptions.all().filter(id=model.pk):
                text_favorit = User.FAVORITE_ICON[True]
                callback_data = f'fav/de&{model.pk}'
            else:
                text_favorit = User.FAVORITE_ICON[False]
                callback_data = f'fav/cr&subscriptions&{model.pk}'
            # snils = self.get_snils(model)
            buttons.append(
                [InlineKeyboardButtonDJ(
                    text=_('🔙 Return to list'),
                    callback_data=self.retun_to_list(
                        self.update.effective_message.reply_markup.inline_keyboard)
                ),
                    InlineKeyboardButtonDJ(
                        text=text_favorit + _('Favorite'),
                        callback_data=callback_data,

                    )])
        return buttons

    def gm_show_list_create_pagination(self, page: int, count_models: int,
                                       first_this_page: int, first_next_page: int,
                                       page_model_amount: int) -> []:
        prev_page_button = InlineKeyboardButtonDJ(
            text=f'⏪',
            callback_data=self.generate_message_callback_data(
                self.command_routings['command_routing_show_list'],
                str(page - 1),
                self.per_page,
                self.columns,
                self.snils
            )
        )
        next_page_button = InlineKeyboardButtonDJ(
            text=f'️⏩',
            callback_data=self.generate_message_callback_data(
                self.command_routings['command_routing_show_list'],
                str(page + 1),
                self.per_page,
                self.columns,
                self.snils
            )
        )

        buttons = []
        if page_model_amount < count_models:
            if (first_this_page > 0) and (first_next_page < count_models):
                buttons = [[prev_page_button, next_page_button]]
            elif first_this_page == 0:
                buttons = [[next_page_button]]
            elif first_next_page >= count_models:
                buttons = [[prev_page_button]]
            else:
                logging.error(
                    f'unreal situation {count_models}, {page_model_amount}, {first_this_page}, {first_next_page}'
                )
        return buttons


class SnilsViewSet(TelegramViewSet):
    viewset_name = 'СНИЛС'
    model_form = SNILSForm
    queryset = SNILS.objects.all()

    actions = ['create', 'show_elem', 'show_list', 'delete']

    meta_texts_dict = {
        'succesfully_deleted': gettext_lazy('The %(viewset_name)s  %(model_id)s is successfully deleted.'),
        'confirm_deleting': gettext_lazy('Are you sure you want to delete %(viewset_name)s  %(model_number)s?'),
        'confirm_delete_button_text': gettext_lazy('🗑 Yes, delete'),
        'gm_next_field': gettext_lazy('Please, fill the field %(label)s\n\n'),
        'gm_success_created': gettext_lazy('The %(viewset_name)s is created! \n\n'),
        'gm_value_error': gettext_lazy('While adding %(label)s the next errors were occurred: %(errors)s\n\n'),
        'gm_self_variant': gettext_lazy('Please, write the value for field %(label)s \n\n'),
        'gm_no_elem': gettext_lazy(
            'The %(viewset_name)s %(model_id)s has not been found 😱 \nPlease try again from the beginning.'
        ),
        'leave_blank_button_text': gettext_lazy('Leave blank'),
    }

    def create(self, field=None, value=None, initial_data=None):
        # todo  проверить не перезаписывает ли программа одни и те же Снилсы
        #  у разных пользователей и как они вообще добовляются при совпадении
        #  номеров у разных пользователей

        initial_data = {
            'users_snils': [f'{self.user.id}']
        }

        return super().create(field, value, initial_data)

    def delete(self, model_or_pk, is_confirmed=False):
        """delete item"""

        model = self.get_orm_model(model_or_pk)

        if model:
            if self.deleting_with_confirm and not is_confirmed:
                # just ask for confirmation
                mess, buttons = self.gm_delete_getting_confirmation(model)
            else:
                # real deleting
                self.user.snilss.remove(model)
                mess, buttons = self.gm_delete_successfully(model)

            return self.CHAT_ACTION_MESSAGE, (mess, buttons)
        else:
            return self.gm_no_elem(model_or_pk)

    def create_or_update_helper(self, field, value, func_response='create', instance=None, initial_data=None):
        is_multichoice_field = self.model_form.base_fields[
                                   field].__class__ == ModelMultipleChoiceField if field else False
        show_field_variants_for_update = (func_response == 'change') and (value is None) and (
                self.update.message is None)
        want_1more_variant_for_multichoice = True
        want_write_self_variant = False
        data = {} if initial_data is None else copy.deepcopy(initial_data)

        # understanding what user has sent
        if (type(field) == str) and field:
            field_value = None
            if value:
                if value == self.WRITE_MESSAGE_VARIANT_SYMBOLS:
                    want_write_self_variant = True
                elif value == self.GO_NEXT_MULTICHOICE_SYMBOLS:
                    want_1more_variant_for_multichoice = False
                elif value == self.NONE_VARIANT_SYMBOLS:
                    data[field] = None
                else:
                    field_value = value
            elif self.update.message:
                field_value = self.update.message.text

            if not field_value is None:
                data[field] = field_value.split(',') if is_multichoice_field else field_value

        want_1more_variant_for_multichoice &= is_multichoice_field  # and len(data.get('field', []))

        form_kwargs = {
            'user': self.user,
            'data': data,
        }
        instance_id = None
        if instance:
            form_kwargs['instance'] = instance
            instance_id = instance.pk

        self.form = self.model_form(**form_kwargs)
        form = self.form

        if want_write_self_variant:
            res = self.gm_self_variant(field, func_response=func_response, instance_id=instance_id)
        else:
            try:
                if len(field_value) <= 10:
                    raise ValueError
                field_value = int(field_value)
                snils = self.queryset.get(number=field_value)
            except ValueError:
                res = self.gm_value_error(
                    field or list(form.fields.keys())[-1],
                    form.errors, func_response=func_response, instance_id=instance_id
                )
            except:
                if not form.is_valid():
                    res = self.gm_value_error(
                        field or list(form.fields.keys())[-1],
                        form.errors, func_response=func_response, instance_id=instance_id
                    )
                else:
                    if not show_field_variants_for_update:
                        form.save(is_completed=not want_1more_variant_for_multichoice)

                    if want_1more_variant_for_multichoice or show_field_variants_for_update:
                        res = self.gm_next_field(
                            field,
                            func_response=func_response,
                            instance_id=instance_id
                        )

                    elif form.next_field:
                        res = self.gm_next_field(
                            form.next_field,
                            func_response=func_response,
                            instance_id=instance_id
                        )
                    else:
                        if func_response == 'create':
                            res = self.gm_success_created(self.form.instance)
                        else:
                            res = self.show_elem(self.form.instance, _('The field has been updated!\n\n'))
            else:
                if self.user not in snils.users_snils.all():
                    snils.users_snils.add(self.user.id)
                res = self.show_elem(snils)
        return res

    def gm_delete_successfully(self, model):
        mess = _(f'SNILS № %(number)s  deleted successfully') % {'number': model.number}
        # mess = f'СНИЛС №{model.number} успешно удален'

        buttons = []
        if 'show_list' in self.actions:
            buttons += [
                [InlineKeyboardButtonDJ(
                    text=_('🔙 Return to list'),
                    callback_data=self.generate_message_callback_data(
                        self.command_routings['command_routing_show_list'],
                    )
                )]
            ]

        return mess, buttons

    def get_queryset(self):
        queryset = SNILS.objects.all()
        if not queryset:
            return super().get_queryset()
        queryset = queryset.filter(users_snils=self.user)
        return queryset

    def gm_show_list_button_names(self, it_m, model) -> str:
        return f'{it_m}. №{model.number}\n'

    def show_list(self, page=0, per_page=10, columns=1, *args, **kwargs):
        __, (mess, buttons) = super().show_list(page, per_page, columns)
        if buttons:
            mess = _('Choose from list or create new')
            # mess = f'Выберите из списка недавних или создайте новый'
        else:
            mess = _('There is nothing here yet\n'
                     'Create a new search')
                    # (f'Здесь пока что ничего нет.\n'
                    # f'Создайте новый поиск')
        buttons += [
            [InlineKeyboardButtonDJ(
                text=_('🔍 New'),
                callback_data='snils/cr'

            ),
                InlineKeyboardButtonDJ(
                    text=_('🔙 Back'),
                    callback_data='start'
                )],
        ]

        return self.CHAT_ACTION_MESSAGE, (mess, buttons)

    def gm_show_elem_create_buttons(self, model, elem_per_raw=2):
        buttons = super().gm_show_elem_create_buttons(model, elem_per_raw)
        for button in buttons:
            if button[0].callback_data.split('&')[0] == 'snils/de':
                text = button[0].text.split('#')
                button[0].text = text[0]
        return buttons

    # todo сделать возможность вводить СНИЛС в любом формате
    def gm_self_variant(self, field_name, mess='', func_response='create', instance_id=None):
        __, (mess, buttons) = super().gm_self_variant(field_name, mess, func_response, instance_id)
        mess = _('Enter SNILS as solid number\n\n'
                 '(No spaces or any separator characters)')
        # mess = ('Введите СНИЛС сплошным числом\n\n'
        #         '(Без пробелов и каких либо разделяющих символов)')
        return __, (mess, buttons)

    def show_elem(self, model_id=None, mess=''):

        model = self.get_orm_model(model_id)

        # generate view of content
        if model:
            if self.use_name_and_id_in_elem_showing:
                mess += f'<b>{self.viewset_name}</b>: № {model.number}'
            # mess += self.gm_show_elem_or_list_fields(model, is_elem=True)

            buttons = self.gm_show_elem_create_buttons(model)
            buttons += [
                [
                    InlineKeyboardButtonDJ(
                        text=_('📃 Display the entire list'),
                        # text='Вывести весь список',
                        callback_data=PassPersonViewSet(
                            telegram_reverse('base:PassPersonViewSet')).gm_callback_data(
                            'show_list',
                            0, 10, 1,
                            model.pk))
                ],
                [
                    InlineKeyboardButtonDJ(
                        text=_('🕵🏼‍♂️ Find a person'),
                        # text='Найти человека',
                        callback_data=f'pas/cr&None&None&None&{model.pk}'
                    )
                ]
            ]
            return self.CHAT_ACTION_MESSAGE, (mess, buttons)
        else:
            return self.gm_no_elem(model_id)

    def gm_delete_getting_confirmation(self, model):
        mess = self.show_texts_dict['confirm_deleting'] % {
            'viewset_name': self.viewset_name,
            'model_number': f'№ {model.number}' or '',
        }
        buttons = [
            [InlineKeyboardButtonDJ(
                text=self.show_texts_dict['confirm_delete_button_text'],
                callback_data=self.gm_callback_data(
                    'delete',
                    model.id,
                    '1'  # True
                )
            )]
        ]
        if 'show_elem' in self.actions:
            buttons += [
                [InlineKeyboardButtonDJ(
                    text=_('🔙 Back'),
                    callback_data=self.gm_callback_data(
                        'show_elem',
                        model.id,
                    )
                )]
            ]
        return mess, buttons


class SubscriptionsViewSet(TelegramViewSet):
    viewset_name = 'Избранное'
    model_form = SubscriptionsForm
    queryset = User.objects.all()
    actions = ['show_list', 'show_elem', 'delete', 'create']

    def get_queryset(self):
        # self.queryset = User.objects.get(id=self.user.id).subscriptions.all()
        self.queryset = self.user.subscriptions.all()
        return self.queryset

    def set_favor_icon(self, method):
        buttons = self.update.effective_message.reply_markup.inline_keyboard
        for button in buttons[0]:
            if button.callback_data.split('&')[0] in ['fav/cr', 'fav/de']:
                match method:
                    case 'create':
                        button.text = User.FAVORITE_ICON[True] + _('Favorite')
                        callback = button.callback_data.replace('/cr&subscriptions', '/de')
                        'fav/de&subscriptions&6'
                        button.callback_data = callback
                    case 'delete':
                        callback = button.callback_data.replace('/de', '/cr&subscriptions')
                        button.callback_data = callback
                        button.text = User.FAVORITE_ICON[False] + _('Favorite')
        mess = self.update.effective_message.text_html
        res = self.CHAT_ACTION_MESSAGE, (mess, buttons)
        return res

    def create(self, field=None, value=None, initial_data=None):
        if field == 'subscriptions':
            self.user.subscriptions.add(value)
            return self.set_favor_icon('create')
        else:
            assert _('dont have value')

    def delete(self, model_or_pk, is_confirmed=False):
        if model_or_pk:
            self.user.subscriptions.remove(model_or_pk)

            return self.set_favor_icon('delete')
        else:
            assert _('dont have model')

    def show_list(self, page=0, per_page=10, columns=1, *args, **kwargs):
        self.get_queryset()
        __, (mess, buttons) = super().show_list(page, per_page, columns)
        if buttons:
            mess = _('Favorite:')
            # mess = f'Избранное:'
        buttons += [
            [InlineKeyboardButtonDJ(
                text=_('🔙 Back'),
                callback_data='start')],
        ]
        return self.CHAT_ACTION_MESSAGE, (mess, buttons)

    def gm_show_list_button_names(self, it_m, model):
        return f'{model}'

    def show_elem(self, model_or_pk, mess=''):
        model = self.get_orm_model(model_or_pk)
        if model:
            mess += self.gm_show_elem_or_list_fields(model, is_elem=True)
            buttons = self._gm_show_elem_create_buttons(model)

            return self.CHAT_ACTION_MESSAGE, (mess, buttons)
        else:
            return self.gm_no_elem(model_or_pk)

    def _gm_show_elem_create_buttons(self, model, elem_per_raw=2):
        buttons = []
        if 'show_list' in self.actions:
            if self.user.subscriptions.all().filter(id=model.pk):
                text_favorit = User.FAVORITE_ICON[True]
                callback_data = f'fav/de&{model.pk}'
            else:
                text_favorit = User.FAVORITE_ICON[False]
                callback_data = f'fav/cr&subscriptions&{model.pk}'

            buttons.append(
                [InlineKeyboardButtonDJ(
                    text=_('🔙 Return to list'),
                    callback_data=self.generate_message_callback_data(
                        self.command_routings['command_routing_show_list'],
                    )
                ),
                    InlineKeyboardButtonDJ(
                        text=text_favorit + _('Favorite'),
                        callback_data=callback_data,

                    )])
        return buttons


class UserViewSet(TGUserViewSet):
    model_form = UserFormNew
    use_name_and_id_in_elem_showing = False

    def show_elem(self, model_id=None, mess=''):
        mess = _('⚙️ Settings:\n\n')
        __, (mess, buttons) = super().show_elem(self.user.id, mess)
        for button in buttons[0]:
            button = button.callback_data.split('&').pop()
            match button:
                case 'telegram_language_code':
                    text = buttons[0][0].text.split()
                    buttons[0][0].text = '🌍  ' + text.pop()
                case 'date':
                    text = buttons[0][1].text.split()
                    buttons[0][1].text = '🔔  ' + text.pop()

        buttons.append([
            InlineKeyboardButtonDJ(
                text=_('🔙 Main menu'),
                callback_data=settings.TELEGRAM_BOT_MAIN_MENU_CALLBACK
            ),
        ])
        mess += _('\nReminder - How many days in advance to remind about the end of the pass')
        return self.CHAT_ACTION_MESSAGE, (mess, buttons)


@handler_decor()
def some_debug_func(bot: TG_DJ_Bot, update: Update, user: User):
    # the message is written in Django notation for translation (with compiling language you can easy translate text)
    message = _(
        'This func is able only in DEBUG mode. press /some_debug_func'
        'to see this elem. By using handler_decor you have user instance %(user)s and some other features'
    ) % {
                  'user': user
              }

    buttons = [[
        InlineKeyboardButtonDJ(
            text=_('🔙 Main menu'),
            callback_data=settings.TELEGRAM_BOT_MAIN_MENU_CALLBACK
        ),
    ]]

    return bot.edit_or_send(update, message, buttons)
