import { useQueries, useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BrainCircuit,
  Clock3,
  Gauge,
  Search,
  TrendingUp,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getOne, getPage } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Input,
  KeyValue,
  LoadingState,
  PageHeader,
  Pagination,
  PartialState,
  Select,
  SourceBadge,
  StatCard,
} from "../../components/common";
import type { Machine, Prediction } from "../../types/api";
import {
  formatRiskLevel,
  formatTimestamp,
  formatValue,
  metricLabel,
  trendLabel,
} from "../../utils/format";

interface MachinePrediction {
  machine: Machine;
  prediction: Prediction;
}

const PREDICTION_BATCH_SIZE = 20;
const API_MACHINE_PAGE_SIZE = 100;

export function predictionMachineWindow(page: number) {
  const safePage = Math.max(1, Math.trunc(page) || 1);
  const absoluteOffset = (safePage - 1) * PREDICTION_BATCH_SIZE;
  return {
    apiPage: Math.floor(absoluteOffset / API_MACHINE_PAGE_SIZE) + 1,
    offset: absoluteOffset % API_MACHINE_PAGE_SIZE,
  };
}

export default function PredictionsPage() {
  const [machinePage, setMachinePage] = useState(1);
  const [hours, setHours] = useState(24);
  const [riskFilter, setRiskFilter] = useState("ALL");
  const [source, setSource] = useState("ALL");
  const [search, setSearch] = useState("");
  const machineWindow = predictionMachineWindow(machinePage);
  const machines = useQuery({
    queryKey: ["machines", "prediction-scope", machineWindow.apiPage],
    queryFn: () =>
      getPage<Machine>("/machines/", { page: machineWindow.apiPage }),
  });
  const analyzedMachines = useMemo(
    () =>
      machines.data?.results.slice(
        machineWindow.offset,
        machineWindow.offset + PREDICTION_BATCH_SIZE,
      ) || [],
    [machineWindow.offset, machines.data?.results],
  );
  const queries = useQueries({
    queries: analyzedMachines.map((machine) => ({
      queryKey: queryKeys.predictions(machine.id, hours),
      queryFn: () =>
        getOne<Prediction[]>(`/machines/${machine.id}/trends/`, {
          params: { hours },
        }),
      staleTime: 60_000,
    })),
  });
  const all = useMemo<MachinePrediction[]>(
    () =>
      queries
        .flatMap((query, index) =>
          (query.data || []).map((prediction) => ({
            machine: analyzedMachines[index],
            prediction,
          })),
        )
        .sort((a, b) => b.prediction.risk_score - a.prediction.risk_score),
    [analyzedMachines, queries],
  );
  const filtered = useMemo(
    () =>
      all.filter(({ machine, prediction }) => {
        const category =
          prediction.risk_score >= 75
            ? "CRITICAL"
            : prediction.risk_score >= 50
              ? "HIGH"
              : prediction.risk_score >= 25
                ? "MODERATE"
                : "LOW";
        return (
          (riskFilter === "ALL" || category === riskFilter) &&
          (source === "ALL" || machine.source_type === source) &&
          (!search ||
            `${machine.hostname} ${prediction.metric_name}`
              .toLowerCase()
              .includes(search.toLowerCase()))
        );
      }),
    [all, riskFilter, search, source],
  );
  const partial = queries.some((query) => query.isError);
  const loading =
    machines.isLoading || queries.some((query) => query.isLoading);
  const counts = {
    critical: all.filter((item) => item.prediction.risk_score >= 75).length,
    high: all.filter(
      (item) =>
        item.prediction.risk_score >= 50 && item.prediction.risk_score < 75,
    ).length,
    breached: all.filter((item) => item.prediction.already_breached).length,
    estimates: all.filter(
      (item) => item.prediction.estimated_threshold_breach_at,
    ).length,
  };
  if (machines.isError)
    return (
      <>
        <PageHeader
          title="Analyse prédictive"
          description="Risques calculés à partir des séries temporelles réelles."
        />
        <ErrorState retry={() => machines.refetch()} />
      </>
    );
  return (
    <div>
      <PageHeader
        title="Risques prédictifs"
        description="Tendances linéaires explicables issues des métriques normalisées. Ces résultats sont des estimations, jamais des certitudes."
        actions={
          <Badge tone="ml">
            <BrainCircuit /> Analyse proactive
          </Badge>
        }
      />
      {partial && (
        <PartialState>
          Une ou plusieurs machines n’ont pas retourné de tendances. Les
          résultats disponibles restent affichés.
        </PartialState>
      )}
      <div className="stats-grid">
        <StatCard
          label="Risques critiques"
          value={counts.critical}
          icon={<Gauge />}
          tone="critical"
        />
        <StatCard
          label="Risques élevés"
          value={counts.high}
          icon={<TrendingUp />}
          tone="warning"
        />
        <StatCard
          label="Seuils déjà franchis"
          value={counts.breached}
          icon={<ArrowUpRight />}
          tone="critical"
        />
        <StatCard
          label="Franchissements estimés"
          value={counts.estimates}
          icon={<Clock3 />}
          tone="ml"
        />
      </div>
      <Card className="resource-card">
        <div className="resource-toolbar">
          <div className="resource-toolbar__title">
            <h2>Analyses par machine et métrique</h2>
            <p>
              Lot courant de 20 machines maximum, avec un maximum de 12
              métriques par machine côté backend. Utilisez la pagination pour
              couvrir tout le parc sans saturer l’API.
            </p>
          </div>
          <div className="filters-bar">
            <label className="search-control">
              <Search />
              <Input
                aria-label="Rechercher un risque"
                placeholder="Machine ou métrique…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <Select
              value={String(hours)}
              onChange={(event) => setHours(Number(event.target.value))}
              aria-label="Fenêtre d’analyse"
            >
              <option value="6">6 heures</option>
              <option value="24">24 heures</option>
              <option value="72">3 jours</option>
              <option value="168">7 jours</option>
              <option value="720">30 jours</option>
            </Select>
            <Select
              value={riskFilter}
              onChange={(event) => setRiskFilter(event.target.value)}
              aria-label="Filtrer par risque"
            >
              <option value="ALL">Tous les risques</option>
              <option value="CRITICAL">Critique ≥ 75</option>
              <option value="HIGH">Élevé ≥ 50</option>
              <option value="MODERATE">Modéré ≥ 25</option>
              <option value="LOW">Faible</option>
            </Select>
            <Select
              value={source}
              onChange={(event) => setSource(event.target.value)}
              aria-label="Filtrer par source"
            >
              <option value="ALL">Toutes les sources</option>
              <option value="WINDOWS">Windows</option>
              <option value="VMWARE">VMware</option>
              <option value="HYPERV">Hyper-V</option>
            </Select>
          </div>
        </div>
        {loading && !all.length ? (
          <LoadingState
            label={`Analyse de ${analyzedMachines.length} machine(s)…`}
          />
        ) : filtered.length ? (
          <div className="prediction-grid prediction-grid--wide">
            {filtered.map(({ machine, prediction }) => {
              const risk = formatRiskLevel(prediction.risk_score);
              return (
                <Card
                  className="prediction-card"
                  key={`${machine.id}-${prediction.metric_name}`}
                >
                  <header>
                    <div>
                      <div className="cluster">
                        <SourceBadge source={machine.source_type} />
                        <Badge tone={risk.tone}>{risk.label}</Badge>
                      </div>
                      <Link to={`/machines/${machine.id}?tab=predictions`}>
                        <h3>{machine.hostname}</h3>
                      </Link>
                      <span>{metricLabel(prediction.metric_name)}</span>
                    </div>
                    <div className={`risk-score risk-score--${risk.tone}`}>
                      <b>{prediction.risk_score}</b>
                      <small>/100</small>
                    </div>
                  </header>
                  <div className="prediction-values">
                    <KeyValue
                      label="Actuel"
                      value={formatValue(
                        prediction.last_value,
                        prediction.unit,
                      )}
                    />
                    <KeyValue
                      label="Moyenne mobile"
                      value={formatValue(
                        prediction.rolling_average,
                        prediction.unit,
                      )}
                    />
                    <KeyValue
                      label="Variation / heure"
                      value={`${formatValue(prediction.rate_of_change_per_hour, prediction.unit)} / h`}
                    />
                    <KeyValue
                      label="Tendance"
                      value={trendLabel(prediction.trend)}
                    />
                  </div>
                  <div className="risk-progress">
                    <span
                      style={{
                        width: `${Math.max(0, Math.min(100, prediction.risk_score))}%`,
                      }}
                    />
                  </div>
                  <div className="prediction-footer">
                    <div>
                      <strong>
                        {prediction.already_breached
                          ? "Seuil déjà franchi"
                          : prediction.estimated_threshold_breach_at
                            ? "Franchissement estimé"
                            : "Aucun franchissement estimé"}
                      </strong>
                      <span>
                        {prediction.estimated_threshold_breach_at
                          ? formatTimestamp(
                              prediction.estimated_threshold_breach_at,
                            )
                          : `${prediction.sample_count} échantillons · ${prediction.confidence}`}
                      </span>
                    </div>
                    <Link
                      aria-label={`Ouvrir ${machine.hostname}`}
                      to={`/machines/${machine.id}?tab=predictions`}
                    >
                      <ArrowUpRight />
                    </Link>
                  </div>
                  <small className="estimate-disclaimer">
                    {prediction.disclaimer}
                  </small>
                </Card>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="Aucun risque prédictif disponible"
            description="Les séries réelles ne contiennent pas encore suffisamment de points ou aucun résultat ne correspond aux filtres."
          />
        )}
        <Pagination
          page={machinePage}
          count={machines.data?.count || 0}
          pageSize={PREDICTION_BATCH_SIZE}
          onPage={setMachinePage}
        />
      </Card>
    </div>
  );
}
