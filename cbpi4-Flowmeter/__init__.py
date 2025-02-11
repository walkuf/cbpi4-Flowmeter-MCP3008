# -*- coding: utf-8 -*-
import os
from aiohttp import web
import logging
from unittest.mock import MagicMock, patch
import asyncio
import random
from cbpi.api import *
import time
from cbpi.api.base import CBPiBase
from cbpi.api import parameters, Property, action
from cbpi.api.step import StepResult, CBPiStep
from cbpi.api.timer import Timer
from voluptuous.schema_builder import message
from cbpi.api.dataclasses import NotificationAction, NotificationType
from cbpi.api.dataclasses import Sensor, Kettle, Props
import Adafruit_GPIO.SPI as SPI
import Adafruit_MCP3008
import logging
from socket import timeout
from typing import KeysView
from cbpi.api.config import ConfigType
import json

logger = logging.getLogger(__name__)

# Software SPI configuration for MCP3008
SPI_PORT   = 0
SPI_DEVICE = 0
mcp = Adafruit_MCP3008.MCP3008(spi=SPI.SpiDev(SPI_PORT, SPI_DEVICE))

class Flowmeter_Config(CBPiExtension):

    def __init__(self, cbpi):
        self.cbpi = cbpi
        self._task = asyncio.create_task(self.init_sensor())

    async def init_sensor(self):
        plugin = await self.cbpi.plugin.load_plugin_list("cbpi4-Flowmeter")
        self.version = plugin[0].get("Version", "0.0.0")
        self.name = plugin[0].get("Name", "cbpi4-Flowmeter")

        self.flowmeter_update = self.cbpi.config.get(self.name + "_update", None)

        unit = self.cbpi.config.get("flowunit", None)
        if unit is None:
            logging.info("INIT FLOW SENSOR CONFIG")
            try:
                await self.cbpi.config.add("flowunit", "L", type=ConfigType.SELECT, description="Flowmeter unit",
                                           source=self.name,
                                           options=[{"label": "L", "value": "L"},
                                                    {"label": "gal(us)", "value": "gal(us)"},
                                                    {"label": "gal(uk)", "value": "gal(uk)"},
                                                    {"label": "qt", "value": "qt"}])

            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
        else:
            if self.flowmeter_update is None or self.flowmeter_update != self.version:
                try:
                    await self.cbpi.config.add("flowunit", unit, type=ConfigType.SELECT, description="Flowmeter unit",
                                               source=self.name,
                                               options=[{"label": "L", "value": "L"},
                                                        {"label": "gal(us)", "value": "gal(us)"},
                                                        {"label": "gal(uk)", "value": "gal(uk)"},
                                                        {"label": "qt", "value": "qt"}])

                except Exception as e:
                    logger.warning('Unable to update config')
                    logger.warning(e)

        if self.flowmeter_update is None or self.flowmeter_update != self.version:
            try:
                await self.cbpi.config.add(self.name + "_update", self.version, type=ConfigType.STRING,
                                           description="Flowmeter Plugin Version",
                                           source='hidden')
            except Exception as e:
                logger.warning('Unable to update config')
                logger.warning(e)
            pass


class FlowMeterData():
    SECONDS_IN_A_MINUTE = 60
    MS_IN_A_SECOND = 1000.0
    enabled = True
    clicks = 0
    lastClick = 0
    clickDelta = 0
    hertz = 0.0
    flow = 0  # in Liters per second
    pour = 0.0  # in Liters

    def __init__(self):
        self.clicks = 0
        self.lastClick = int(time.time() * FlowMeterData.MS_IN_A_SECOND)
        self.clickDelta = 0
        self.hertz = 0.0
        self.flow = 0.0
        self.pour = 0.0
        self.enabled = True

    def update(self, currentTime, scale):
        self.clicks += 1
        self.clickDelta = max((currentTime - self.lastClick), 1)
        if self.enabled is True and self.clickDelta < 1000:
            self.hertz = FlowMeterData.MS_IN_A_SECOND / self.clickDelta
            self.flow = self.hertz / (FlowMeterData.SECONDS_IN_A_MINUTE * scale)  # In Liters per second
            instPour = self.flow * (self.clickDelta / FlowMeterData.MS_IN_A_SECOND)
            self.pour += instPour
        self.lastClick = currentTime

    def clear(self):
        self.pour = 0
        return str(self.pour)


@parameters([Property.Number(label="Scale Flow 1", configurable=True, description="Scale for Flow Sensor 1"),
             Property.Number(label="Scale Flow 2", configurable=True, description="Scale for Flow Sensor 2")])
class FlowSensor(CBPiSensor):

    def __init__(self, cbpi, id, props):
        super(FlowSensor, self).__init__(cbpi, id, props)
        self.value = 0
        self.fms = dict()
        self.channel = self.props.get("Channel", 0)
        self.sensorShow = self.props.get("Display", "Total Volume")
        self.scaleFlow1 = self.props.get("Scale Flow 1", 7.5)
        self.scaleFlow2 = self.props.get("Scale Flow 2", 7.5)
        self.fms[0] = FlowMeterData()
        self.fms[2] = FlowMeterData()

    @action(key="Reset Sensor", parameters=[])
    async def Reset(self, **kwargs):
        self.reset()
        print("RESET FLOWSENSOR")

    def get_unit(self):
        unit = self.cbpi.config.get("flowunit", "L")
        if self.sensorShow == "Flow, unit/s":
            unit = unit + "/s"
        return unit

    def read_channel(self, channel):
        return mcp.read_adc(channel)

    def doAClick(self, channel):
        currentTime = int(time.time() * FlowMeterData.MS_IN_A_SECOND)
        scale = self.scaleFlow1 if channel == 0 else self.scaleFlow2
        self.fms[channel].update(currentTime, float(scale))

    def convert(self, inputFlow):
        unit = self.cbpi.config.get("flowunit", "L")
        if unit == "gal(us)":
            inputFlow = inputFlow * 0.264172052
        elif unit == "gal(uk)":
            inputFlow = inputFlow * 0.219969157
        elif unit == "qt":
            inputFlow = inputFlow * 1.056688
        if self.sensorShow == "Flow, unit/s":
            inputFlow = "{0:.2f}".format(inputFlow)
        else:
            inputFlow = "{0:.2f}".format(inputFlow)
        return inputFlow

    async def run(self):
        while self.running is True:
            if self.sensorShow == "Total volume":
                flow1 = self.fms[0].pour
                flow2 = self.fms[2].pour
                flowConverted1 = self.convert(flow1)
                flowConverted2 = self.convert(flow2)
                self.value = (float(flowConverted1), float(flowConverted2))
            elif self.sensorShow == "Flow, unit/s":
                flow1 = self.fms[0].flow
                flow2 = self.fms[2].flow
                flowConverted1 = self.convert(flow1)
                flowConverted2 = self.convert(flow2)
                self.value = (float(flowConverted1), float(flowConverted2))
            else:
                logging.info("FlowSensor error")

            self.push_update(self.value)
            await asyncio.sleep(1)

    def getValue(self):
        flow = self.fms[0].pour
        flowConverted = self.convert(flow)
        return flowConverted

    def reset(self):
        logging.info("Reset Flowsensor")
        self.fms[0].clear()
        self.fms[2].clear()
        return "Ok"

    def get_state(self):
        return dict(value=self.value)


@parameters([Property.Number(label="Scale Temp 1", configurable=True, description="Scale for Temperature Sensor 1"),
             Property.Number(label="Scale Temp 2", configurable=True, description="Scale for Temperature Sensor 2")])
class TempSensor(CBPiSensor):

    def __init__(self, cbpi, id, props):
        super(TempSensor, self).__init__(cbpi, id, props)
        self.value = 0
        self.channel = self.props.get("Channel", 1)
        self.scaleTemp1 = self.props.get("Scale Temp 1", 1.0)
        self.scaleTemp2 = self.props.get("Scale Temp 2", 1.0)

    def read_channel(self, channel):
        return mcp.read_adc(channel)

    def convert_temp(self, raw_value, scale):
        # Assuming the raw_value needs to be converted to temperature using a scale factor
        return raw_value * scale

    async def run(self):
        while self.running is True:
            if self.channel == 1:
                raw_value = self.read_channel(1)
                self.value = self.convert_temp(raw_value, self.scaleTemp1)
            elif self.channel == 3:
                raw_value = self.read_channel(3)
                self.value = self.convert_temp(raw_value, self.scaleTemp2)
            self.push_update(self.value)
            await asyncio.sleep(1)

    def reset(self):
        logging.info("Reset Temperature sensor")
        self.value = 0
        return "Ok"

    def get_state(self):
        return dict(value=self.value)


def setup(cbpi):
    cbpi.plugin.register("FlowSensor", FlowSensor)
    cbpi.plugin.register("TempSensor", TempSensor)
    cbpi.plugin.register("Flowmeter_Config", Flowmeter_Config)
    pass
