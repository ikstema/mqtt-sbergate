# devices/light.py
import logging

from devices.utils.color_converter import ColorConverter
from devices.utils.linear_converter import LinearConverter
from .base_entity import BaseEntity

LIGHT_ENTITY_CATEGORY = "light"
logger = logging.getLogger(__name__)

class LightEntity(BaseEntity):
    supported_features: int = 0
    max_mireds: int = 500
    min_mireds: int = 153
    supported_color_modes: list[str] = []
    current_state: bool = False
    current_sber_brightness: int = 0
    current_sber_color_temp: int = 0
    current_color_mode: str = None

    brightness_converter: LinearConverter = LinearConverter()
    color_temp_converter: LinearConverter = LinearConverter()
    color_temp_converter.set_reversed(True)

    _COLOUR_MODES = {
        "xy",
        "hs",
        "rgb",
        "rgbw",
        "rgbww",
        "rgbcw",
        "rgbcct",
    }

    _BRIGHTNESS_MODES = _COLOUR_MODES | {
        "brightness",
        "color_temp",
        "white",
        "warmwhite",
        "coldwhite",
    }

    def __init__(self, ha_entity_data: dict):
        super().__init__(LIGHT_ENTITY_CATEGORY, ha_entity_data)
        self.current_state = ha_entity_data.get("state", "off") == "on"

        self.brightness_converter.set_ha_limits(0, 255)
        self.brightness_converter.set_sber_limits(50, 1000)

        self.color_temp_converter.set_ha_limits(153, 500)
        self.color_temp_converter.set_sber_limits(0, 1000)

    def fill_by_ha_state(self, ha_state):
        super().fill_by_ha_state(ha_state)

        self.max_mireds = ha_state["attributes"].get("max_mireds", 500)
        self.min_mireds = ha_state["attributes"].get("min_mireds", 153)
        if self.max_mireds is not None and self.min_mireds is not None:
            self.color_temp_converter.set_ha_limits(self.min_mireds, self.max_mireds)

        self.current_state = ha_state.get("state", "off") == "on"
        ha_brightness = ha_state["attributes"].get("brightness", 0)
        ha_brightness = int(ha_brightness) if ha_brightness is not None else 0

        self.current_sber_brightness = self.brightness_converter.ha_to_sber(ha_brightness)

        ha_color_temp = ha_state["attributes"].get("color_temp", 0)
        if ha_color_temp is not None:
            self.current_sber_color_temp = self.color_temp_converter.ha_to_sber(ha_color_temp)
        else:
            self.current_sber_color_temp = None

        self.current_color_mode = ha_state["attributes"].get("color_mode", None)
        self.supported_features = ha_state["attributes"].get("supported_features", 0)
        self.supported_color_modes = ha_state["attributes"].get("supported_color_modes", [])

        self.hs_color = ha_state["attributes"].get("hs_color", None)    # [26.767, 32.827]
        self.rgb_color = ha_state["attributes"].get("rgb_color", None)  # [255, 209, 171]
        self.xy_color = ha_state["attributes"].get("xy_color", None)    # [0.413, 0.364]

    def create_features_list(self):
        """Формирует список фич, которые поддерживает данный класс"""
        features = super().create_features_list() # Когда вызывается 'тот метод?'
        features += ["on_off"]

        colour_supported = self._supports_colour()
        brightness_supported = self._supports_brightness()

        if brightness_supported:
            features.append("light_brightness")

        if colour_supported:
            features += [
                "light_colour",
                "light_mode",
            ]

        if "color_temp" in self._normalized_color_modes():
            features += ["light_colour_temp"]

        return features

    def create_allowed_values_list(self):
        """Формирует список допустимых значений"""
        allowed_values = {}

        if self._supports_brightness():
            allowed_values["light_brightness"] = {
                "type": "INTEGER",
                "integer_values": {"min": 50, "max": 1000}
            }
        if self._supports_colour():
            allowed_values["light_colour"] = {
                "type": "COLOUR",
            }
            allowed_values["light_mode"] = {
                "type": "ENUM",
                "enum_values": {
                    "values": [
                        "white",
                        "colour"
                    ]
                }
            }

        if "color_temp" in self._normalized_color_modes():
            allowed_values["light_colour_temp"] = {
                "type": "INTEGER",
                "integer_values": {
                    "min": 0,
                    "max": 1000
                }
            }

        return allowed_values

    def to_sber_state(self):  # Really it is to_sber_entity
        """Формирует состояние для Сбер"""
        res = super().to_sber_state()
        if res is None:
            return None
        

        res["model"] |= {
            "features": self.create_features_list(),
            "allowed_values": self.create_allowed_values_list()
        }

        return res

    def _is_current_color_mode_colored(self):
        return self.current_color_mode not in ["white", "color_temp"]

    def to_sber_current_state(self):
        """
        Метод выполняет трансляцию текущего состояния светового прибора, записанное в данном объекте в состояние sber.
        Состояние sber содержит массив пар "Ключ" - "Значение", которые описывают ряд параметров прибора.
        Часть параметров доступны не всегда.
        """
        states = [{
                "key": "on_off",
                "value": {
                    "type": "BOOL",
                    "bool_value": self.current_state
                }
            }]


        if self._supports_brightness() and self.current_sber_brightness != 0:
            states.append({
                "key": "light_brightness",
                "value": {
                    "type": "INTEGER",
                    "integer_value": self.current_sber_brightness
                }
            })

        if self.current_state: # on/off == on
            if self._is_current_color_mode_colored() and isinstance(self.hs_color, list) and len(self.hs_color) >= 2:
                current_color_sber = ColorConverter.ha_to_sber_hsv(self.hs_color[0], self.hs_color[1], self.current_sber_brightness)
                states.append({
                    "key": "light_colour",
                    "value": {
                        "type": "COLOUR",
                        "colour_value": { "h": current_color_sber[0], "s": current_color_sber[1], "v": current_color_sber[2] }
                    }}
                )
                states.append({
                    "key": "light_mode",
                    "value": {
                        "type": "ENUM",
                        "enum_value": "colour"
                    }
                })
            else:
                if self.current_sber_color_temp is not None:
                    states.append({
                        "key": "light_colour_temp",
                        "value": {
                            "type": "INTEGER",
                            "integer_value": self.current_sber_color_temp
                        }
                    })
                states.append({
                    "key": "light_mode",
                    "value": {
                        "type": "ENUM",
                        "enum_value": "white"
                    }
                })

        return {
            self.entity_id: {
                "states": states
            }
        }

    # --- Методы ---
    def process_cmd(self, cmd_data):
        """Обрабатывает команду от Sber на HA
        Команда поступает как набор пар "Ключ" - "Значение", которые описывают параметры, которые sber хочет выставить в HA.
        Один из параметров (light_mode) напрямую в HA не выставляется, а выставляется только локально. И относительно него дальше идет передача состояния обратно в sber.
        На выходе метода получаем массив словарей, которые или описывают команду для HA, или запрашивают обновление состояния sber для текущего устройства. Если словарь имеет ключ url, он отправляется в виде json-объекта
        на HA, если update_state, то на сбер просто передается измененное состояние объекта.
        """

        processing_result = []

        if cmd_data is None:
            return None

        for data_item in cmd_data.get("states", []):
            cmd_key = data_item.get("key", "")
            cmd_value = data_item.get("value", {})

            if cmd_key == "on_off" and cmd_value.get("type", "") == "BOOL":
                new_state = cmd_value.get("bool_value", False)

                self.current_state = new_state
                processing_result.append({
                    "url": {
                        "type": "call_service",
                        "domain": "light",
                        "service": "turn_on" if new_state else "turn_off",
                        "target": {
                            "entity_id": self.entity_id
                        }
                    }
                })

            if cmd_key == "light_brightness":
                sber_br_value = int(cmd_value.get("integer_value", 50))
                ha_br_value = self.brightness_converter.sber_to_ha(sber_br_value)

                brightness = max(50, min(int(ha_br_value), 255))
                if self.current_state:
                    processing_result.append({
                        "url": {
                            "type": "call_service",
                            "domain": "light",
                            "service": "turn_on",
                            "service_data": { "brightness": brightness,},
                            "target": {
                                "entity_id": self.entity_id
                            }
                        }
                    })

            if cmd_key == "light_colour":
                hsv_color = cmd_value.get("colour_value", None)
                if hsv_color is not None:
                    color = ColorConverter.sber_to_ha_hsv(
                        min(hsv_color.get("h", 0), 360), 
                        min(hsv_color.get("s", 0), 1000), 
                        min(hsv_color.get("v", 0), 1000))
                else:
                    color = ColorConverter.ha_to_sber_hsv(0, 0, 0)

                if self.current_state:
                    processing_result.append({
                        "url": {
                            "type": "call_service",
                            "domain": "light",
                            "service": "turn_on",
                            "service_data": { 
                                "hs_color": [color[0], color[1]],
                                "brightness": color[2],
                            },
                            "target": {
                                "entity_id": self.entity_id
                            }
                        }
                    })

# Sber MQTT Command: {'devices': {'light.spoty_lev_sp': {'states': [{'key': 'light_mode', 'value': {'type': 'ENUM', 'enum_value': 'colour'}}, {'key': 'light_colour', 'value': {'type': 'COLOUR', 'colour_value': {'v': 100}}}]}}}
# Тут пока странно. Похоже, в HA нет команды прямого перехода в режим color_temp. Видимо, надо работать через локальное состояние или по содержимому color_temp и цветов.
# После ряда исследований оказалось, что в ha вообще нет заморочки за режим - прислали ему color_temp - он установит температуру, прислали цвет - выставит цвет.
# Возможно нам нужно отслеживать этот режим у нас внутри. И в зависимости от этого режима уже выставлять температуру или цвет на ha.
            if cmd_key == "light_mode": 
                mode_value = cmd_value.get("enum_value", None)
                self.current_color_mode = "xy" if mode_value == "colour" else "white"
                processing_result.append({"update_state": True})

            if cmd_key == "light_colour_temp":
                sber_color_temp = int(cmd_value.get("integer_value", 0))  #[0, 1000] - нет. У нас стоит явное ограничение и сбер его выдерживает. Масштабировать не нужно.
                if sber_color_temp is None:
                    sber_color_temp = 0
                
                ha_color_temp = self.color_temp_converter.sber_to_ha(sber_color_temp)


                if self.current_state:
                    processing_result.append({
                        "url": {
                            "type": "call_service",
                            "domain": "light",
                            "service": "turn_on",
                            "service_data": { "color_temp": ha_color_temp, },
                            "target": {
                                "entity_id": self.entity_id
                            }
                        }
                    })

        logger.debug(f"(LightEntity.process_cmd) Command: {cmd_key}, processing res: {processing_result}")
        return processing_result

    def process_state_change(self, old_state, new_state):
        self.fill_by_ha_state(new_state)

    def _normalized_color_modes(self) -> set[str]:
        if not isinstance(self.supported_color_modes, list):
            return set()
        return {str(mode).lower() for mode in self.supported_color_modes if isinstance(mode, str)}

    def _supports_colour(self) -> bool:
        modes = self._normalized_color_modes()
        return bool(modes & self._COLOUR_MODES)

    def _supports_brightness(self) -> bool:
        modes = self._normalized_color_modes()
        if modes:
            if modes == {"onoff"}:
                return False
            return bool((modes & self._BRIGHTNESS_MODES) or len(modes - {"onoff"}) > 0)

        return bool(self.supported_features and (self.supported_features & 1))
                