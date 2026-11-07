# Facade

- Status: use
- Profiles: web, software
- Family: structural

## Problem it solves

Callers must coordinate several steps of a subsystem, such as an API with authentication, retries and unit conversion, and they repeat that logic in many places.

## Use it when

The same multi-step sequence against a subsystem appears in more than one place.

## Do not use it when

It would wrap a single call, or hide something the callers really need.

## Signs you do not need it yet

Only one place talks to the subsystem.

## Simpler alternative

A module with a few well-named functions. That is already a facade.

## How it looks when misused

A facade that grows until it exposes everything. A facade that still leaks the subsystem's types to its callers.

## Minimal example

```js
const API = "https://api.example.com";

export async function getForecast(city) {
  const response = await fetch(`${API}/forecast?city=${encodeURIComponent(city)}`);
  if (!response.ok) throw new Error(`Forecast request failed with status ${response.status}`);
  const data = await response.json();
  return { city, celsius: data.temperature.value };
}
```

## References

- Original: Gamma, Helm, Johnson, Vlissides. Design Patterns. Addison-Wesley, 1994.
- Free: https://refactoring.guru/design-patterns/facade
