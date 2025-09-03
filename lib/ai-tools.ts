import { tool } from "ai"
import { z } from "zod"

// Prefer env for flexibility; falls back to localhost for dev.
const API_BASE = (typeof process !== "undefined" && process.env.NEXT_PUBLIC_BACKEND_URL) || "http://localhost:5000/api"

// Small helper to add per-call timeouts and consistent JSON handling
async function fetchJSON<T>(url: string, init?: RequestInit, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController()
  const t = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(url, { ...init, signal: controller.signal })
    if (!res.ok) throw new Error(`HTTP ${res.status} on ${url}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(t)
  }
}

// Tool for Usage Analyzer Agent
export const getEnergyUsageSummary = tool({
  description:
    "Analyzes the user's overall energy usage patterns, including peak usage hours and total consumption across morning, afternoon, evening, night.",
  // The AI SDK expects a JSON Schema for parameters. Keep an object, even if empty.
  inputSchema: z.object({}) as any,
  // execute is the correct field for the tool handler in AI SDK v5.
  execute: async () => {
    try {
      return await fetchJSON(`${API_BASE}/peak`)
    } catch (error) {
      console.error("Error fetching energy usage summary:", error)
      return {
        error: `Failed to fetch energy usage summary: ${error instanceof Error ? error.message : String(error)}`,
      }
    }
  },
})

// Tool for Device Optimizer Agent
export const getDeviceConsumptionData = tool({
  description:
    "Retrieves detailed energy consumption data for all devices, including current power, total energy, peak usage, and efficiency status.",
  inputSchema: z.object({}),
  execute: async () => {
    try {
      return await fetchJSON(`${API_BASE}/devices`)
    } catch (error) {
      console.error("Error fetching device consumption data:", error)
      return {
        error: `Failed to fetch device consumption data: ${error instanceof Error ? error.message : String(error)}`,
      }
    }
  },
})

// Tool for Tariff Mapper & Bill Predictor Agent
export const getPredictedBillAndTariff = tool({
  description:
    "Forecasts energy consumption and bill based on current patterns and tiered tariff rules; returns total and slab-wise breakdown.",
  inputSchema: z.object({
    days: z.number().int().min(1).max(365).optional().describe("Number of days to predict (default 30)."),
  }),
  execute: async ({ days = 30 }) => {
    try {
      return await fetchJSON(`${API_BASE}/predict?days=${encodeURIComponent(days)}`)
    } catch (error) {
      console.error("Error fetching predicted bill and tariff data:", error)
      return {
        error: `Failed to fetch predicted bill and tariff data: ${
          error instanceof Error ? error.message : String(error)
        }`,
      }
    }
  },
})

// Tool for Energy Saver Advisor Agent
export const getSpecificDeviceDetails = tool({
  description:
    "Retrieves granular details for a specific device: hourly/daily usage patterns, status, and suggestions.",
  inputSchema: z.object({
    deviceName: z
      .string()
      .min(1)
      .describe("The exact device name (e.g., 'AC', 'Fridge', 'Television', 'Light', 'Fan', 'Washing Machine')."),
  }),
  execute: async ({ deviceName }) => {
    try {
      return await fetchJSON(`${API_BASE}/device/${encodeURIComponent(deviceName)}`)
    } catch (error) {
      console.error(`Error fetching details for device ${deviceName}:`, error)
      return {
        error: `Failed to fetch details for ${deviceName}: ${error instanceof Error ? error.message : String(error)}`,
      }
    }
  },
})

// Tool for general energy saving suggestions
export const getGeneralEnergySuggestions = tool({
  description: "Fetches general energy-saving suggestions derived from the system based on overall patterns.",
  inputSchema: z.object({}),
  execute: async () => {
    try {
      return await fetchJSON(`${API_BASE}/suggestions`)
    } catch (error) {
      console.error("Error fetching general energy suggestions:", error)
      return {
        error: `Failed to fetch general energy suggestions: ${error instanceof Error ? error.message : String(error)}`,
      }
    }
  },
})

// Weather context tool
export const getWeatherData = tool({
  description: "Fetches current weather data for a specified city: temperature, condition, humidity.",
  inputSchema: z.object({
    city: z.string().min(1).describe("City name (e.g., 'Chennai', 'Delhi', 'Mumbai')."),
  }) as any,
  execute: async ({ city }) => {
    try {
      return await fetchJSON(`${API_BASE}/weather?city=${encodeURIComponent(city)}`)
    } catch (error) {
      console.error(`Error fetching weather data for ${city}:`, error)
      return {
        error: `Failed to fetch weather data for ${city}: ${error instanceof Error ? error.message : String(error)}`,
      }
    }
  },
})
