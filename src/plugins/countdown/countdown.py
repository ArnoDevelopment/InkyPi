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
        # Disable the global style panel; Countdown provides per-item style controls
        template_params['style_settings'] = False
        template_params['supported_languages'] = SUPPORTED_LANGUAGES
        return template_params

    def generate_image(self, settings, device_config):
        title = settings.get('title')

        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]
        
        timezone = device_config.get_config("timezone", default="America/New_York")
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)

        dirname = os.path.dirname(__file__)
        locale_dir = os.path.join(dirname, 'locale')

        gettext.bindtextdomain("countdown", locale_dir)
        gettext.textdomain("countdown")

        # utility to read list-like values from settings (support keys with [] suffix)
        def _get_list(key):
            if key in settings:
                return settings[key]
            if f"{key}[]" in settings:
                return settings[f"{key}[]"]
            return None

        # support multiple dates via `dates` (key or list field) or legacy single `date`
        dates_val = _get_list('dates') or _get_list('date') or settings.get('date')
        if not dates_val:
            raise RuntimeError("At least one date is required.")

        # gather per-item fields
        titles_list = _get_list('titles') or _get_list('title')
        textcolors_list = _get_list('textColors') or _get_list('textColor')

        # parse provided dates into normalized list
        raw_dates = []
        if isinstance(dates_val, list):
            raw_dates = dates_val
        else:
            # split on newlines or commas
            raw_dates = [d.strip() for d in str(dates_val).replace(',', '\n').split('\n') if d.strip()]

        # parse per-date backgrounds (one per line, mapping by index)
        backgrounds_val = _get_list('dateBackgrounds') or _get_list('backgroundImageFile')
        backgrounds_list = []
        if backgrounds_val:
            if isinstance(backgrounds_val, list):
                backgrounds_list = backgrounds_val
            else:
                backgrounds_list = [b.strip() for b in str(backgrounds_val).replace(',', '\n').split('\n') if b.strip()]

        # Build candidate occurrences (date objects) with metadata: {'orig':raw, 'date':date_obj, 'has_year':bool, 'background':...}
        candidates = []
        today = current_time.date()
        for raw in raw_dates:
            try:
                parts = raw.split('-')
                if len(parts) == 3:
                    # YYYY-MM-DD
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    cand_date = datetime(y, m, d, tzinfo=tz).date()
                    # attach background by index if available
                    idx = len(candidates)
                    bg = backgrounds_list[idx] if idx < len(backgrounds_list) else None
                    candidates.append({'index': idx, 'orig': raw, 'date': cand_date, 'has_year': True, 'background': bg})
                elif len(parts) == 2:
                    # MM-DD recurring yearly -> next occurrence from today
                    m, d = int(parts[0]), int(parts[1])
                    try:
                        this_year = datetime(today.year, m, d).date()
                    except ValueError:
                        continue
                    if this_year >= today:
                        occ = this_year
                    else:
                        # next year
                        occ = datetime(today.year + 1, m, d).date()
                    idx = len(candidates)
                    bg = backgrounds_list[idx] if idx < len(backgrounds_list) else None
                    candidates.append({'index': idx, 'orig': raw, 'date': occ, 'has_year': False, 'background': bg})
                else:
                    # try parsing as YYYY/MM/DD or fallback
                    try:
                        parsed = datetime.fromisoformat(raw).date()
                        idx = len(candidates)
                        bg = backgrounds_list[idx] if idx < len(backgrounds_list) else None
                        candidates.append({'index': idx, 'orig': raw, 'date': parsed, 'has_year': True, 'background': bg})
                    except Exception:
                        continue
            except Exception:
                continue

        if not candidates:
            raise RuntimeError("No valid dates provided.")

        # Find nearest future candidate (smallest non-negative delta)
        future_candidates = []
        for c in candidates:
            delta = (c['date'] - today).days
            if delta >= 0:
                future_candidates.append((delta, c))

        if future_candidates:
            # pick minimal delta
            future_candidates.sort(key=lambda x: (x[0], x[1]['date']))
            chosen = future_candidates[0][1]
            day_count = future_candidates[0][0]
            # For recurring dates without year, show the original raw as title if no title provided
        else:
            # No future dates, compute nearest past occurrence
            past_candidates = []
            for c in candidates:
                # For recurring (no year), compute the most recent past occurrence
                if not c['has_year']:
                    m, d = [int(p) for p in c['orig'].split('-')]
                    try:
                        this_year = datetime(today.year, m, d).date()
                    except ValueError:
                        continue
                    if this_year <= today:
                        occ = this_year
                    else:
                        occ = datetime(today.year - 1, m, d).date()
                    past_date = occ
                else:
                    past_date = c['date']
                delta = (past_date - today).days
                if delta <= 0:
                    past_candidates.append((abs(delta), delta, c, past_date))
            # after collecting past candidates, pick the nearest
            if not past_candidates:
                # fallback: use earliest candidate
                c = sorted(candidates, key=lambda x: x['date'])[0]
                chosen = c
                day_count = (c['date'] - today).days
            else:
                # pick the smallest absolute delta (closest in past)
                past_candidates.sort(key=lambda x: (x[0], x[3]))
                _, delta, c, past_date = past_candidates[0]
                chosen = c
                day_count = delta

        # chosen contains the selected occurrence; set countdown_date from it
        countdown_date = datetime.combine(chosen['date'], datetime.min.time())
        countdown_date = tz.localize(countdown_date)

        # determine per-item title/language/textColor and selected background
        idx = chosen.get('index') if isinstance(chosen, dict) else None

        def _pick_per_item_value(value_list, idx, fallback=None):
            if isinstance(value_list, (list, tuple)):
                if idx is not None and idx < len(value_list):
                    return value_list[idx]
                return fallback
            if value_list is not None:
                return value_list if idx == 0 or idx is None else fallback
            return fallback

        # selected title: per-item titles list or legacy single title
        title = _pick_per_item_value(titles_list, idx, title)

        # global language setting uses countdown-wide language only
        sel_language = settings.get('language')

        # selected text color
        sel_text_color = _pick_per_item_value(textcolors_list, idx, None)

        # if a per-date background was provided, set it into plugin settings so template picks it up
        plugin_settings = dict(settings) if settings is not None else {}
        chosen_bg = chosen.get('background') if isinstance(chosen, dict) else None
        if chosen_bg:
            plugin_settings['backgroundImageFile'] = chosen_bg
            plugin_settings['backgroundOption'] = 'image'
        # set per-item text color if available
        if sel_text_color:
            plugin_settings['textColor'] = sel_text_color

        # apply selected language for translations
        language = sel_language or 'en_US'
        try:
            locale.setlocale(locale.LC_ALL, (language, "UTF-8"))
        except Exception:
            try:
                locale.setlocale(locale.LC_ALL, language)
            except Exception:
                locale.setlocale(locale.LC_ALL, '')

        try:
            translation = gettext.translation("countdown", locale_dir, languages=[language])
            translation.install()
            _ = translation.gettext
        except Exception:
            _ = gettext.gettext

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
            "plugin_settings": plugin_settings
        }

        image = self.render_image(dimensions, "countdown.html", "countdown.css", template_params)
        return image