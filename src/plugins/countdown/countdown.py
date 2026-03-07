from plugins.base_plugin.base_plugin import BasePlugin
from plugins.countdown.constants import (
    SUPPORTED_LANGUAGES
)
from PIL import Image
from datetime import datetime, timezone
import logging
import pytz
import gettext
import locale

import os

logger = logging.getLogger(__name__)
class Countdown(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['supported_languages'] = SUPPORTED_LANGUAGES
        return template_params

    def generate_image(self, settings, device_config):
        title = settings.get('title')
        countdown_date_str = settings.get('date')
        language = settings.get('language', 'en_US')

        if not countdown_date_str:
            raise RuntimeError("Date is required.")

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        timezone = device_config.get_config("timezone", default="America/New_York")
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)

        locale.setlocale(locale.LC_ALL, (language, "UTF-8"))
        dirname = os.path.dirname(__file__)
        locale_dir = os.path.join(dirname, 'locale')
        gettext.bindtextdomain("countdown", locale_dir)
        gettext.textdomain("countdown")

        translation = gettext.translation("countdown", locale_dir, languages=[language])
        translation.install()
        _ = translation.gettext

        countdown_date = datetime.strptime(countdown_date_str, "%Y-%m-%d")
        countdown_date = tz.localize(countdown_date)

        day_count = (countdown_date.date() - current_time.date()).days

        if day_count == 0:
            before_label = ""
            days = title
            title = ""
            after_label = ""
        else:
            days = abs(day_count)
            if day_count > 0:
                text = _('{0} Day Left') if days == 1 else _('{0} Days Left')
            else:
                text = _('{0} Day Passed') if days == 1 else _('{0} Days Passed')

            values = text.split("{0}")

            before_label = values[0]
            after_label = values[1]

        date_format = "%-d %B"
        if countdown_date.date().year != current_time.date().year:
            date_format += " %Y"

        template_params = {
            "title": title,
            "date": countdown_date.strftime(date_format),
            "day_count": days,
            "before_label": before_label,
            "after_label": after_label,
            "plugin_settings": settings
        }

        image = self.render_image(dimensions, "countdown.html", "countdown.css", template_params)
        return image