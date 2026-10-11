package io.github.devdooly.platformlab.demo;

public record SensorEvent(String eventId, String sensorId, String eventTime, Double value) {}
