"use client"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { TrendingUp, BarChart3, PieChart, Calendar, Zap, Clock, Target, Award, Cpu } from "lucide-react"
import ProfessionalChart from "@/components/professional-chart"

interface AnalyticsProps {
  energyData: any[]
  dashboardData: any
  deviceData: any
}

export default function Analytics({ energyData, dashboardData, deviceData }: AnalyticsProps) {
  const deviceEntries = Object.entries(deviceData)
  const totalDevices = deviceEntries.length
  const activeDevices = deviceEntries.filter(([_, data]: [string, any]) => data.currentPower > 0).length

  // New categorical efficiency model
  const properCount =
    totalDevices > 0 ? deviceEntries.filter(([_, data]: [string, any]) => data.efficiencyStatus === "proper").length : 0
  const improperCount = totalDevices - properCount
  const properRate = totalDevices > 0 ? (properCount / totalDevices) * 100 : 0

  const performanceMetrics = [
    { label: "Proper Devices", value: properRate, target: 90, color: "green" },
    { label: "Cost Optimization", value: 73, target: 80, color: "emerald" },
    { label: "Peak Load Management", value: 65, target: 75, color: "orange" },
    {
      label: "Device Utilization",
      value: (activeDevices / Math.max(totalDevices, 1)) * 100,
      target: 85,
      color: "purple",
    },
  ]

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Energy Analytics</h1>
          <p className="text-gray-600">Comprehensive analysis of your smart home energy consumption</p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant="outline">
            <Calendar className="h-3 w-3 mr-1" />
            Last 30 Days
          </Badge>
          <Badge variant="outline">
            <Cpu className="h-3 w-3 mr-1" />
            {totalDevices} Devices
          </Badge>
        </div>
      </div>

      {/* Performance Overview */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {performanceMetrics.map((metric) => (
          <Card key={metric.label}>
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-medium text-gray-600">{metric.label}</h3>
                <Target className="h-4 w-4 text-gray-400" />
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-2xl font-bold text-gray-900">{metric.value.toFixed(1)}%</span>
                  <span className="text-sm text-gray-500">Target: {metric.target}%</span>
                </div>
                <Progress value={metric.value} className="h-2" />
                <div className="flex items-center space-x-1">
                  {metric.value >= metric.target ? (
                    <Award className="h-3 w-3 text-green-600" />
                  ) : (
                    <TrendingUp className="h-3 w-3 text-orange-600" />
                  )}
                  <span className={`text-xs ${metric.value >= metric.target ? "text-green-600" : "text-orange-600"}`}>
                    {metric.value >= metric.target ? "Target achieved" : "Needs improvement"}
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Device Performance Comparison */}
      <Card>
        <CardHeader>
          <CardTitle>Device Performance Comparison</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {deviceEntries.map(([deviceName, data]: [string, any]) => (
              <div key={deviceName} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div className="flex items-center space-x-4">
                  <div className="font-medium text-gray-900">{deviceName}</div>
                  <Badge variant={data.currentPower > 0 ? "default" : "secondary"}>
                    {data.currentPower > 0 ? "Active" : "Idle"}
                  </Badge>
                </div>
                <div className="flex items-center space-x-6 text-sm">
                  <div className="text-center">
                    <div className="font-medium text-blue-600">{data.currentPower.toFixed(1)}W</div>
                    <div className="text-gray-500">Power</div>
                  </div>
                  <div className="text-center">
                    <div className="font-medium text-green-600">{data.totalEnergy.toFixed(2)}kWh</div>
                    <div className="text-gray-500">Energy</div>
                  </div>
                  <div className="text-center">
                    <Badge variant={data.efficiencyStatus === "proper" ? "default" : "destructive"}>
                      {data.efficiencyStatus === "proper" ? "Proper" : "Improper"}
                    </Badge>
                    <div className="text-gray-500 mt-1">Status</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Detailed Analytics */}
      <Tabs defaultValue="consumption" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="consumption" className="flex items-center space-x-2">
            <BarChart3 className="h-4 w-4" />
            <span>Consumption</span>
          </TabsTrigger>
          <TabsTrigger value="patterns" className="flex items-center space-x-2">
            <Clock className="h-4 w-4" />
            <span>Patterns</span>
          </TabsTrigger>
          <TabsTrigger value="efficiency" className="flex items-center space-x-2">
            <Zap className="h-4 w-4" />
            <span>Efficiency</span>
          </TabsTrigger>
          <TabsTrigger value="costs" className="flex items-center space-x-2">
            <PieChart className="h-4 w-4" />
            <span>Costs</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="consumption" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Device Energy Consumption</CardTitle>
              </CardHeader>
              <CardContent>
                <ProfessionalChart
                  data={Object.fromEntries(
                    deviceEntries.map(([name, data]: [string, any]) => [name, data.totalEnergy]),
                  )}
                  type="doughnut"
                  height={300}
                />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Power Usage Comparison</CardTitle>
              </CardHeader>
              <CardContent>
                <ProfessionalChart
                  data={deviceEntries.map(([name, data]: [string, any]) => ({ name, power: data.currentPower }))}
                  type="bar"
                  height={300}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Consumption Statistics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                <div className="text-center">
                  <div className="text-3xl font-bold text-blue-600">
                    {deviceEntries.reduce((sum, [_, data]: [string, any]) => sum + data.totalEnergy, 0).toFixed(1)} kWh
                  </div>
                  <p className="text-sm text-gray-600">Total Consumption</p>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-green-600">
                    {deviceEntries.reduce((sum, [_, data]: [string, any]) => sum + data.currentPower, 0).toFixed(1)} W
                  </div>
                  <p className="text-sm text-gray-600">Current Load</p>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-orange-600">
                    {Math.max(...deviceEntries.map(([_, data]: [string, any]) => data.peakUsage)).toFixed(1)} W
                  </div>
                  <p className="text-sm text-gray-600">Peak Demand</p>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-purple-600">
                    {activeDevices}/{totalDevices}
                  </div>
                  <p className="text-sm text-gray-600">Active Devices</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="patterns" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Time-of-Day Usage</CardTitle>
              </CardHeader>
              <CardContent>
                <ProfessionalChart data={dashboardData?.peak?.period_kwh} type="doughnut" height={300} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Device Activity Patterns</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {deviceEntries.map(([deviceName, data]: [string, any]) => (
                  <div key={deviceName} className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-medium">{deviceName}</span>
                      <span className="text-sm text-gray-600">{data.currentPower > 0 ? "Active" : "Idle"}</span>
                    </div>
                    <Progress value={data.currentPower > 0 ? 100 : 0} className="h-2" />
                  </div>
                ))}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="efficiency" className="space-y-6">
          {/* Status Overview */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Overall Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Proper</span>
                  <span className="text-lg font-bold text-green-600">{properCount}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-gray-600">Improper</span>
                  <span className="text-lg font-bold text-red-600">{improperCount}</span>
                </div>
                <div className="pt-2">
                  <div className="flex items-center justify-between text-sm mb-1">
                    <span className="text-gray-600">Proper Rate</span>
                    <span className="font-medium">{properRate.toFixed(1)}%</span>
                  </div>
                  <Progress value={properRate} className="h-2" />
                </div>
              </CardContent>
            </Card>

            {deviceEntries.slice(0, 2).map(([deviceName, data]: [string, any]) => (
              <Card key={deviceName}>
                <CardHeader>
                  <CardTitle>{deviceName} Status</CardTitle>
                </CardHeader>
                <CardContent className="text-center">
                  <div
                    className={`text-3xl font-bold mb-2 ${
                      data.efficiencyStatus === "proper" ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {data.efficiencyStatus === "proper" ? "Proper" : "Improper"}
                  </div>
                  <p className="text-sm text-gray-600">
                    {data.efficiencyStatus === "proper"
                      ? "Within expected operating pattern"
                      : "Unstable pattern detected - review suggested"}
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Efficiency Status by Device</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {deviceEntries.map(([deviceName, data]: [string, any]) => (
                  <div key={deviceName} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <span className="font-medium">{deviceName}</span>
                    <Badge variant={data.efficiencyStatus === "proper" ? "default" : "destructive"}>
                      {data.efficiencyStatus === "proper" ? "Proper" : "Improper"}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="costs" className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Device Cost Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  {deviceEntries.map(([deviceName, data]: [string, any]) => {
                    const estimatedCost = (data.totalEnergy * 5).toFixed(2) // Rough estimate at ₹5/kWh
                    return (
                      <div key={deviceName} className="flex justify-between items-center p-3 bg-gray-50 rounded-lg">
                        <span className="font-medium">{deviceName}</span>
                        <div className="text-right">
                          <div className="font-bold">₹{estimatedCost}</div>
                          <div className="text-xs text-gray-500">{data.totalEnergy.toFixed(2)} kWh</div>
                        </div>
                      </div>
                    )
                  })}
                  <div className="flex justify-between items-center p-3 bg-blue-50 border border-blue-200 rounded-lg">
                    <span className="font-bold text-blue-800">Total Estimated Cost</span>
                    <span className="font-bold text-blue-800">
                      ₹
                      {deviceEntries
                        .reduce((sum, [_, data]: [string, any]) => sum + data.totalEnergy * 5, 0)
                        .toFixed(2)}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Cost Optimization Opportunities</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="p-3 bg-green-50 border border-green-200 rounded-lg">
                    <div className="font-medium text-green-800 mb-1">Proper Devices</div>
                    <div className="text-sm text-green-700">
                      {deviceEntries
                        .filter(([_, data]: [string, any]) => data.efficiencyStatus === "proper")
                        .map(([name]) => name)
                        .join(", ") || "None"}
                    </div>
                  </div>
                  <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                    <div className="font-medium text-red-800 mb-1">Needs Attention</div>
                    <div className="text-sm text-red-700">
                      {deviceEntries
                        .filter(([_, data]: [string, any]) => data.efficiencyStatus === "improper")
                        .map(([name]) => name)
                        .join(", ") || "None"}
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
