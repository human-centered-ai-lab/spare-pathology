import { useState, useCallback, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import type {
  EvaluationStatus,
  EvaluationData,
  FilterOptions,
} from "@/types";
import { Users, BookOpen, RefreshCw, ExternalLink } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";

import { BoxPlot } from "@/components/charts/box-plot";
import { ForestPlot } from "@/components/charts/forest-plot";
import { PassRateChart } from "@/components/charts/pass-rate-chart";
import { FailureModesChart } from "@/components/charts/failure-modes-chart";

const ALL_VALUE = "__all__";

interface EvaluationTabProps {
  studyId: number;
}

interface Filters {
  submitted_only: boolean;
  group_by: string;
  attribute_filters: Record<string, string[]>;
  user_ids: number[];
}

interface NotebookInfo {
  enabled: boolean;
  url: string | null;
  filename: string | null;
  exists: boolean;
}

export function EvaluationTab({ studyId }: EvaluationTabProps) {
  const [filters, setFilters] = useState<Filters>({
    submitted_only: true,
    group_by: "",
    attribute_filters: {},
    user_ids: [],
  });

  // --- Notebook ---
  const { data: notebookInfo } = useQuery<NotebookInfo>({
    queryKey: ["admin", "studies", String(studyId), "notebook"],
    queryFn: () => api.get<NotebookInfo>(`/api/admin/studies/${studyId}/notebook`),
  });

  const openNotebook = useMutation({
    mutationFn: () => api.post<NotebookInfo>(`/api/admin/studies/${studyId}/notebook`),
    onSuccess: (result) => {
      if (result.url) {
        window.open(result.url, "_blank");
      }
    },
  });

  const updateFilter = useCallback(
    <K extends keyof Filters>(key: K, value: Filters[K]) => {
      setFilters((prev) => ({ ...prev, [key]: value }));
    },
    [],
  );

  // Fetch filter options
  const { data: filterOptions } = useQuery<FilterOptions>({
    queryKey: ["admin", "studies", String(studyId), "evaluation", "filter-options"],
    queryFn: () =>
      api.get<FilterOptions>(
        `/api/admin/studies/${studyId}/evaluation/filter-options`,
      ),
    staleTime: 5 * 60 * 1000,
  });

  const toggleFilterValue = useCallback((attrName: string, value: string) => {
    setFilters((prev) => {
      const fromOptions =
        filterOptions?.attributes?.find((a) => a.name === attrName)?.values.map(String) ?? [];
      const current = prev.attribute_filters[attrName] ?? fromOptions;
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      return { ...prev, attribute_filters: { ...prev.attribute_filters, [attrName]: next } };
    });
  }, [filterOptions?.attributes]);

  const toggleAllFilterValues = useCallback((attrName: string, allValues: string[]) => {
    setFilters((prev) => {
      const fromOptions =
        filterOptions?.attributes?.find((a) => a.name === attrName)?.values.map(String) ?? [];
      const current = prev.attribute_filters[attrName] ?? fromOptions;
      const allSelected = current.length === allValues.length;
      return { ...prev, attribute_filters: { ...prev.attribute_filters, [attrName]: allSelected ? [] : [...allValues] } };
    });
  }, [filterOptions?.attributes]);

  const effectiveUserIds = useMemo(() => {
    if (filters.user_ids.length > 0) return filters.user_ids;
    return (filterOptions?.users ?? []).map((u) => u.id);
  }, [filters.user_ids, filterOptions?.users]);

  const effectiveAttributeFilters = useMemo(() => {
    if (Object.keys(filters.attribute_filters).length > 0) {
      return filters.attribute_filters;
    }
    const initial: Record<string, string[]> = {};
    for (const attr of filterOptions?.attributes ?? []) {
      initial[attr.name] = attr.values.map(String);
    }
    return initial;
  }, [filters.attribute_filters, filterOptions?.attributes]);

  // Fetch evaluation status
  const { data: status, isLoading: statusLoading } =
    useQuery<EvaluationStatus>({
      queryKey: ["admin", "studies", String(studyId), "evaluation", "status"],
      queryFn: () =>
        api.get<EvaluationStatus>(
          `/api/admin/studies/${studyId}/evaluation/status`,
        ),
      staleTime: 60 * 1000,
    });

  // Build query params for evaluation data
  const buildParams = useCallback(() => {
    const params = new URLSearchParams();
    params.set("submitted_only", String(filters.submitted_only));
    if (filters.group_by) params.set("group_by", filters.group_by);
    for (const [key, values] of Object.entries(effectiveAttributeFilters)) {
      if (values.length === 0) continue;
      const attrDef = filterOptions?.attributes?.find((a) => a.name === key);
      if (attrDef && values.length === attrDef.values.length) continue;
      params.set(key, values.join(","));
    }
    if (effectiveUserIds.length > 0) {
      params.set("user_ids", effectiveUserIds.join(","));
    }
    return params.toString();
  }, [filters, filterOptions, effectiveAttributeFilters, effectiveUserIds]);

  // Fetch evaluation data
  const { data: evalData, isLoading: evalLoading } =
    useQuery<EvaluationData>({
      queryKey: [
        "admin",
        "studies",
        String(studyId),
        "evaluation",
        "data",
        buildParams(),
      ],
      queryFn: () =>
        api.get<EvaluationData>(
          `/api/admin/studies/${studyId}/evaluation/data?${buildParams()}`,
        ),
      staleTime: 60 * 1000,
    });

  const toggleUser = useCallback((userId: number) => {
    setFilters((prev) => {
      const defaultIds = (filterOptions?.users ?? []).map((u) => u.id);
      const baseIds = prev.user_ids.length > 0 ? prev.user_ids : defaultIds;
      const ids = baseIds.includes(userId)
        ? baseIds.filter((id) => id !== userId)
        : [...baseIds, userId];
      return { ...prev, user_ids: ids };
    });
  }, [filterOptions?.users]);

  const boxPlotData = useMemo(() => {
    const distrib = evalData?.score_distributions;
    if (!distrib || !distrib.groups || Object.keys(distrib.groups).length === 0) return null;
    const entries: { label: string; scores: number[]; mean: number; median: number; q1: number; q3: number; count: number }[] = [];
    for (const [label, stats] of Object.entries(distrib.groups)) {
      entries.push({
        label,
        scores: stats.scores ?? [],
        mean: stats.mean ?? 0,
        median: stats.median ?? 0,
        q1: stats.q1 ?? 0,
        q3: stats.q3 ?? 0,
        count: stats.count ?? 0,
      });
    }
    return entries.length > 0 ? entries : null;
  }, [evalData?.score_distributions]);

  const forestPlotData =
    evalData?.center_effects && evalData.center_effects.effects.length > 0
      ? evalData.center_effects
      : null;

  const passRates = useMemo(() => {
    const gc = evalData?.group_comparison;
    if (!gc?.pass_rates) return null;
    const rates: Record<string, number> = {};
    for (const [key, val] of Object.entries(gc.pass_rates)) {
      rates[key] = (val as number) * 100;
    }
    return Object.keys(rates).length > 0 ? rates : null;
  }, [evalData?.group_comparison]);

  const mannWhitneyP = useMemo(() => {
    const gc = evalData?.group_comparison;
    if (!gc?.score_comparison) return null;
    const sc = gc.score_comparison;
    if ("mannwhitney_p" in sc) {
      return sc.mannwhitney_p as number | null;
    }
    return null;
  }, [evalData?.group_comparison]);

  const messages = [
    ...(evalData?.validation?.warnings ?? []),
    evalData?.icc?.message,
    evalData?.fleiss_kappa?.message,
    evalData?.center_effects?.message,
    evalData?.group_comparison?.message,
    evalData?.score_distributions?.message,
    evalData?.breakdowns?.message,
  ].filter((m): m is string => !!m);

  return (
    <div className="space-y-4">
      {/* Filter */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Filter</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-3">
          {/* Dynamic attribute filters (multi-select) */}
          {(filterOptions?.attributes ?? []).map((attr) => {
            const allVals = attr.values.map(String);
            const selected = effectiveAttributeFilters[attr.name] ?? [];
            const allSelected = selected.length === allVals.length;
            return (
              <DropdownMenu key={attr.name}>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="h-8 text-sm">
                    {attr.name}
                    <Badge variant="secondary" className="ml-1 text-[10px] px-1 py-0">
                      {selected.length}
                    </Badge>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="max-h-[300px] overflow-y-auto">
                  <DropdownMenuCheckboxItem
                    checked={allSelected}
                    onCheckedChange={() => toggleAllFilterValues(attr.name, allVals)}
                    onSelect={(e) => e.preventDefault()}
                  >
                    All
                  </DropdownMenuCheckboxItem>
                  <DropdownMenuSeparator />
                  {allVals.map((v) => (
                    <DropdownMenuCheckboxItem
                      key={v || "__empty__"}
                      checked={selected.includes(v)}
                      onCheckedChange={() => toggleFilterValue(attr.name, v)}
                      onSelect={(e) => e.preventDefault()}
                    >
                      {v || <span className="text-muted-foreground italic">none</span>}
                    </DropdownMenuCheckboxItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            );
          })}

          {/* Group by dropdown */}
          <Select
            value={filters.group_by || ALL_VALUE}
            onValueChange={(v) => updateFilter("group_by", v === ALL_VALUE ? "" : v)}
          >
            <SelectTrigger className="h-8 w-auto min-w-[130px] text-sm">
              <SelectValue placeholder="Group by..." />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_VALUE}>No grouping</SelectItem>
              {(filterOptions?.attributes ?? []).map((attr) => (
                <SelectItem key={attr.name} value={attr.name}>
                  Group by {attr.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Multi-select for users */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="h-8">
                <Users className="h-3.5 w-3.5" />
                Users
                {effectiveUserIds.length > 0 && (
                  <Badge variant="secondary" className="ml-1">
                    {effectiveUserIds.length}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="max-h-[300px] overflow-y-auto">
              {filterOptions?.users.map((u) => (
                <DropdownMenuCheckboxItem
                  key={u.id}
                  checked={effectiveUserIds.includes(u.id)}
                  onCheckedChange={() => toggleUser(u.id)}
                  onSelect={(e) => e.preventDefault()}
                >
                  {u.name}
                </DropdownMenuCheckboxItem>
              ))}
              {(!filterOptions?.users || filterOptions.users.length === 0) && (
                <p className="text-muted-foreground text-xs px-2 py-1.5">
                  No users available
                </p>
              )}
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="flex items-center gap-2 ml-auto">
            <Switch
              id="submitted-only"
              checked={filters.submitted_only}
              onCheckedChange={(checked) =>
                updateFilter("submitted_only", checked === true)
              }
            />
            <Label htmlFor="submitted-only" className="text-sm">
              Submitted only
            </Label>
          </div>
        </CardContent>
      </Card>

      {/* Summary */}
      {(statusLoading || evalLoading) ? (
        <Skeleton className="h-28 w-full" />
      ) : (status || evalData) ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-3 sm:grid-cols-6 gap-4">
              {status && (
                <>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">Submitted</p>
                    <p className="text-xl font-bold text-success">{status.submitted}</p>
                    <p className="text-[10px] text-muted-foreground">{status.total_users} total</p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">In Progress</p>
                    <p className="text-xl font-bold text-warning">{status.in_progress}</p>
                    <p className="text-[10px] text-muted-foreground">{status.total_users} total</p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">Not Started</p>
                    <p className="text-xl font-bold text-muted-foreground">{status.not_started}</p>
                    <p className="text-[10px] text-muted-foreground">{status.total_users} total</p>
                  </div>
                </>
              )}
              {evalData && (
                <>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">ICC</p>
                    <p className="text-xl font-bold">
                      {evalData.icc.value != null ? Number(evalData.icc.value).toFixed(3) : "N/A"}
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">Fleiss' Kappa</p>
                    <p className="text-xl font-bold">
                      {evalData.fleiss_kappa.value != null ? Number(evalData.fleiss_kappa.value).toFixed(3) : "N/A"}
                    </p>
                  </div>
                  <div className="space-y-0.5">
                    <p className="text-xs text-muted-foreground">Mann-Whitney p</p>
                    <p className="text-xl font-bold">
                      {mannWhitneyP != null ? Number(mannWhitneyP).toFixed(3) : "N/A"}
                    </p>
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* Messages from backend */}
      {messages.length > 0 && (
        <Card>
          <CardContent className="pt-4 space-y-1">
            {messages.map((msg, i) => (
              <p key={i} className="text-muted-foreground text-sm">{msg}</p>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Charts */}
      {evalData && (
        <div className="grid grid-cols-2 gap-4">
          {boxPlotData && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Score Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <BoxPlot data={boxPlotData} />
              </CardContent>
            </Card>
          )}

          {forestPlotData && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Center Effects</CardTitle>
              </CardHeader>
              <CardContent>
                <ForestPlot data={forestPlotData} />
              </CardContent>
            </Card>
          )}

          {passRates && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Pass Rates</CardTitle>
              </CardHeader>
              <CardContent>
                <PassRateChart data={passRates} />
              </CardContent>
            </Card>
          )}

          {evalData.failure_modes &&
            Object.keys(evalData.failure_modes.overall).length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Failure Modes</CardTitle>
                </CardHeader>
                <CardContent>
                  <FailureModesChart data={evalData.failure_modes} />
                </CardContent>
              </Card>
            )}

          {evalData.breakdowns &&
            Object.keys(evalData.breakdowns.groups).length > 0 && (
              <Card className="col-span-2">
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Group Breakdowns</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b">
                          <th className="text-left py-2 px-3 font-medium">Group</th>
                          <th className="text-right py-2 px-3 font-medium">Count</th>
                          <th className="text-right py-2 px-3 font-medium">Mean Score</th>
                          <th className="text-right py-2 px-3 font-medium">Std</th>
                          <th className="text-right py-2 px-3 font-medium">Pass Rate</th>
                          <th className="text-right py-2 px-3 font-medium">Raters</th>
                          <th className="text-right py-2 px-3 font-medium">Images</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(evalData.breakdowns.groups).map(([group, stats]) => (
                          <tr key={group} className="border-b last:border-0">
                            <td className="py-2 px-3 font-medium">{group}</td>
                            <td className="text-right py-2 px-3">{stats.count}</td>
                            <td className="text-right py-2 px-3">{stats.mean_score.toFixed(2)}</td>
                            <td className="text-right py-2 px-3">{stats.std_score.toFixed(2)}</td>
                            <td className="text-right py-2 px-3">
                              {stats.pass_rate != null ? `${(stats.pass_rate * 100).toFixed(1)}%` : "N/A"}
                            </td>
                            <td className="text-right py-2 px-3">{stats.n_raters}</td>
                            <td className="text-right py-2 px-3">{stats.n_images}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>
            )}
        </div>
      )}
      {/* Notebook */}
      {notebookInfo?.enabled && <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">Analysis Notebook</CardTitle>
              <CardDescription>
                Open an interactive Jupyter notebook with this study's data pre-loaded as a pandas DataFrame.
              </CardDescription>
            </div>
            <Button
              className="shrink-0 ml-4"
              onClick={() => openNotebook.mutate()}
              disabled={openNotebook.isPending}
            >
              {openNotebook.isPending ? (
                <RefreshCw className="size-4 animate-spin" />
              ) : (
                <BookOpen className="size-4" />
              )}
              {notebookInfo?.exists ? "Open Notebook" : "Create Notebook"}
              <ExternalLink className="size-3 ml-1 opacity-50" />
            </Button>
          </div>
        </CardHeader>
      </Card>}
    </div>
  );
}
