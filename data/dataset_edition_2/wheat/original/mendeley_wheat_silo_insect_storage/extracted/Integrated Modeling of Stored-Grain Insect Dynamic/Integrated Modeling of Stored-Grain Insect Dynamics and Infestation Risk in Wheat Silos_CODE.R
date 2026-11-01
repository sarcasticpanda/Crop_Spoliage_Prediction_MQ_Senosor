################################################################################
# insect_models.R
# Insect Population Dynamics in Stored-Grain Silos
################################################################################

# ============================================================
# REQUIRED PACKAGES
# ============================================================

library(readxl)
library(dplyr)
library(ggplot2)

library(glmmTMB)
library(DHARMa)
library(splines)

library(brms)
library(bayesplot)

library(patchwork)
library(lubridate)
library(tidyr)
library(cmdstanr)
# ── 1. Data preparation ──────────────────────────────────────────────

data_file <- file.choose()

df <- read_excel(data_file)

# Clean column names
names(df) <- trimws(names(df))

df <- df %>%
  mutate(
    # Correct sampling dates:
    # Time_Index 1–13 = 1997, Time_Index 14–15 = 1998
    Date_fixed = lubridate::make_date(
      year  = if_else(Time_Index <= 13, 1997L, 1998L),
      month = lubridate::month(Date),
      day   = lubridate::day(Date)
    ),
    
    # Factors
    Species   = factor(Species),
    Zone      = factor(Zone, levels = c("CENTER", "MIDDLE", "EDGE")),
    Trap_type = factor(
      Trap_type,
      levels = c("Trap_2m", "Trap_top", "Trier")
    ),
    Silo = factor(
      as.character(Silo),
      levels = c("1", "2", "3")
    ),
    
    # Continuous variables
    Temperature = as.numeric(Temperature),
    Humidity    = as.numeric(Humidity),
    
    # Standardized covariates
    Temp_std = as.numeric(scale(Temperature)),
    Hum_std  = as.numeric(scale(Humidity)),
    Time_std = as.numeric(scale(Time_Index))
  )

# Basic data checks
cat(sprintf(
  "Data: %d rows, %d columns\n",
  nrow(df), ncol(df)
))

cat(sprintf(
  "Sampling dates: %s to %s\n",
  min(df$Date_fixed), max(df$Date_fixed)
))

cat(sprintf(
  "Time_Index: %d to %d\n",
  min(df$Time_Index), max(df$Time_Index)
))
# ── 2. Exploratory Data Analysis ─────────────────────────────────────

# 2a. Distribution of counts
p1 <- ggplot(df, aes(x = Count)) +
  geom_histogram(bins = 50, fill = "steelblue", alpha = 0.8) +
  scale_y_log10() +
  geom_vline(
    xintercept = mean(df$Count, na.rm = TRUE),
    color = "red",
    linetype = "dashed"
  ) +
  labs(
    title = "Distribution of insect counts",
    x = "Count",
    y = "Frequency (log scale)"
  ) +
  theme_minimal()


# 2b. Temporal trends by species
p2 <- df %>%
  group_by(Species, Time_Index) %>%
  summarise(
    Mean_Count = mean(Count, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  ggplot(aes(
    x = Time_Index,
    y = Mean_Count,
    color = Species
  )) +
  geom_line(linewidth = 1) +
  geom_point(size = 2) +
  scale_x_continuous(breaks = 1:15) +
  labs(
    title = "Temporal trajectories by species",
    x = "Sampling occasion",
    y = "Mean count"
  ) +
  theme_minimal()


# 2c. Environmental conditions over time
env_time <- df %>%
  group_by(Time_Index) %>%
  summarise(
    Temperature = mean(Temperature, na.rm = TRUE),
    `Grain moisture content` = mean(Humidity, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  tidyr::pivot_longer(
    cols = c(Temperature, `Grain moisture content`),
    names_to = "Variable",
    values_to = "Value"
  )

p3 <- ggplot(
  env_time,
  aes(x = Time_Index, y = Value)
) +
  geom_line(linewidth = 1) +
  geom_point(size = 2) +
  facet_wrap(
    ~ Variable,
    scales = "free_y",
    ncol = 1
  ) +
  scale_x_continuous(breaks = 1:15) +
  labs(
    title = "Environmental conditions over time",
    x = "Sampling occasion",
    y = NULL
  ) +
  theme_minimal()


# 2d. Counts by sampling category and silo
p4 <- ggplot(
  df,
  aes(x = Trap_type, y = Count, fill = Trap_type)
) +
  geom_boxplot(alpha = 0.7) +
  labs(
    title = "Counts by sampling category",
    x = "Sampling category",
    y = "Count"
  ) +
  theme_minimal() +
  theme(legend.position = "none")


p5 <- ggplot(
  df,
  aes(x = Silo, y = Count, fill = Silo)
) +
  geom_boxplot(alpha = 0.7) +
  labs(
    title = "Counts by silo",
    x = "Silo",
    y = "Count"
  ) +
  theme_minimal() +
  theme(legend.position = "none")


# 2e. Proportion of zero counts over time
p6 <- df %>%
  group_by(Time_Index) %>%
  summarise(
    Zero_Rate = mean(Count == 0, na.rm = TRUE) * 100,
    .groups = "drop"
  ) %>%
  ggplot(aes(x = Time_Index, y = Zero_Rate)) +
  geom_col(fill = "lightcoral", color = "darkred") +
  scale_x_continuous(breaks = 1:15) +
  labs(
    title = "Zero counts over time",
    x = "Sampling occasion",
    y = "Zero counts (%)"
  ) +
  theme_minimal()


# 2f. Temperature–moisture relationship by season
p7 <- df %>%
  mutate(
    Season = case_when(
      lubridate::month(Date_fixed) %in% c(6, 7, 8)  ~ "Summer",
      lubridate::month(Date_fixed) %in% c(9, 10, 11) ~ "Autumn",
      lubridate::month(Date_fixed) %in% c(12, 1, 2)  ~ "Winter",
      TRUE ~ NA_character_
    ),
    Season = factor(
      Season,
      levels = c("Summer", "Autumn", "Winter")
    )
  ) %>%
  ggplot(
    aes(
      x = Temperature,
      y = Humidity,
      color = Season,
      shape = Season
    )
  ) +
  geom_point(size = 3, alpha = 0.8) +
  labs(
    title = "Temperature and grain moisture content by season",
    x = "Grain temperature (°C)",
    y = "Grain moisture content (%)"
  ) +
  theme_minimal()
# ------------------------------------------------------------
# 2g. Descriptive summaries for reporting
# ------------------------------------------------------------

overall_descriptive <- df %>%
  summarise(
    N = n(),
    Mean_Count = mean(Count, na.rm = TRUE),
    SD_Count = sd(Count, na.rm = TRUE),
    Median_Count = median(Count, na.rm = TRUE),
    Variance_Count = var(Count, na.rm = TRUE),
    Variance_to_Mean = Variance_Count / Mean_Count,
    Zero_Percent = 100 * mean(Count == 0, na.rm = TRUE),
    Min_Count = min(Count, na.rm = TRUE),
    Max_Count = max(Count, na.rm = TRUE),
    Temp_Min = min(Temperature, na.rm = TRUE),
    Temp_Max = max(Temperature, na.rm = TRUE),
    Temp_Mean = mean(Temperature, na.rm = TRUE),
    
    Moisture_Min = min(Humidity, na.rm = TRUE),
    Moisture_Max = max(Humidity, na.rm = TRUE),
    Moisture_Mean = mean(Humidity, na.rm = TRUE)
  )


species_descriptive <- df %>%
  group_by(Species) %>%
  summarise(
    Mean_Count = mean(Count, na.rm = TRUE),
    SD_Count = sd(Count, na.rm = TRUE),
    Median_Count = median(Count, na.rm = TRUE),
    Zero_Percent = 100 * mean(Count == 0, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  arrange(desc(Mean_Count))


temporal_descriptive <- df %>%
  group_by(Time_Index) %>%
  summarise(
    Mean_Count = mean(Count, na.rm = TRUE),
    SE_Count = sd(Count, na.rm = TRUE) /
      sqrt(sum(!is.na(Count))),
    Zero_Percent = 100 * mean(Count == 0, na.rm = TRUE),
    Mean_Temperature = mean(Temperature, na.rm = TRUE),
    Mean_Grain_Moisture = mean(Humidity, na.rm = TRUE),
    .groups = "drop"
  )


overall_peak <- temporal_descriptive %>%
  slice_max(
    Mean_Count,
    n = 1,
    with_ties = FALSE
  )


species_peaks <- df %>%
  group_by(Species, Time_Index) %>%
  summarise(
    Mean_Count = mean(Count, na.rm = TRUE),
    .groups = "drop"
  ) %>%
  group_by(Species) %>%
  slice_max(
    Mean_Count,
    n = 1,
    with_ties = FALSE
  ) %>%
  ungroup()


cat("\n=== OVERALL DESCRIPTIVE SUMMARY ===\n")
print(overall_descriptive, width = Inf)

cat("\n=== SPECIES-SPECIFIC SUMMARY ===\n")
print(species_descriptive, n = Inf, width = Inf)

cat("\n=== TEMPORAL SUMMARY ===\n")
print(temporal_descriptive, n = Inf, width = Inf)

cat("\n=== OVERALL OBSERVED PEAK ===\n")
print(overall_peak, width = Inf)

cat("\n=== SPECIES-SPECIFIC OBSERVED PEAKS ===\n")
print(species_peaks, n = Inf, width = Inf)

# Save complete EDA overview
ggsave(
  "eda_overview.png",
  (p1 | p2) /
    (p3 | p6) /
    (p4 | p5 | p7),
  width = 15,
  height = 13,
  dpi = 150
)
# ------------------------------------------------------------
# Save main descriptive Figure 1
# ------------------------------------------------------------

figure1_descriptive <- (
  p1 | p2 | p3
) / (
  p6 | p4 | p7
) +
  patchwork::plot_annotation(
    tag_levels = "A"
  )

ggsave(
  filename = "Figure1_descriptive_overview.png",
  plot = figure1_descriptive,
  width = 16,
  height = 8.5,
  units = "in",
  dpi = 300,
  bg = "white"
)

print(figure1_descriptive)
# ── 3. Population trajectory ─────────────────────────────────────────

# Sampling-date lookup table
time_key <- df %>%
  distinct(Time_Index, Date_fixed) %>%
  arrange(Time_Index) %>%
  mutate(
    Month = lubridate::month(Date_fixed),
    Season = case_when(
      Month %in% c(6, 7, 8)   ~ "Summer",
      Month %in% c(9, 10, 11) ~ "Autumn",
      Month %in% c(12, 1, 2)  ~ "Winter",
      TRUE ~ NA_character_
    ),
    Season = factor(
      Season,
      levels = c("Summer", "Autumn", "Winter")
    ),
    Label = format(Date_fixed, "%d %b")
  )

# 3a. Overall population trajectory (Mean ± SE)
df_pop <- df %>%
  group_by(Time_Index) %>%
  summarise(
    Mean = mean(Count, na.rm = TRUE),
    SE   = sd(Count, na.rm = TRUE) / sqrt(sum(!is.na(Count))),
    .groups = "drop"
  ) %>%
  left_join(time_key, by = "Time_Index")

p_pop <- ggplot(df_pop, aes(x = Time_Index, y = Mean)) +
  
  # Season shading
  geom_rect(
    data = time_key,
    aes(
      xmin = Time_Index - 0.5,
      xmax = Time_Index + 0.5,
      ymin = -Inf,
      ymax = Inf,
      fill = Season
    ),
    alpha = 0.15,
    inherit.aes = FALSE
  ) +
  
  scale_fill_manual(
    values = c(
      "Summer" = "red",
      "Autumn" = "gold",
      "Winter" = "lightblue"
    )
  ) +
  
  # Mean ± SE
  geom_ribbon(
    aes(
      ymin = Mean - SE,
      ymax = Mean + SE
    ),
    alpha = 0.2
  ) +
  
  geom_line(
    color = "blue",
    linewidth = 1.2
  ) +
  
  geom_point(
    color = "blue",
    size = 2
  ) +
  
  scale_x_continuous(
    breaks = time_key$Time_Index,
    labels = time_key$Label
  ) +
  
  labs(
    title = "Overall population trajectory",
    x = "Sampling occasion",
    y = "Mean count ± SE"
  ) +
  
  theme_minimal() +
  
  theme(
    axis.text.x = element_text(
      angle = 45,
      hjust = 1
    ),
    legend.position = "none"
  )


# 3b. Count vs grain temperature
p_temp <- ggplot(
  df,
  aes(x = Temperature, y = Count)
) +
  
  geom_point(
    alpha = 0.3,
    color = "blue"
  ) +
  
  stat_summary_bin(
    bins = 10,
    fun = mean,
    geom = "line",
    color = "red",
    linewidth = 1.2
  ) +
  
  labs(
    title = "Count vs grain temperature",
    subtitle = "Red line = binned mean",
    x = "Grain temperature (°C)",
    y = "Count"
  ) +
  
  theme_minimal()

# Combined descriptive figure
population_fig <- p_pop / p_temp

ggsave(
  "population_overview.png",
  population_fig,
  width = 12,
  height = 10,
  dpi = 150
)
# ============================================================
# 4. FREQUENTIST COUNT MODELS
# ============================================================
# Hum_std = grain moisture content (%)
# ------------------------------------------------------------
# 4.1 Poisson model
# ------------------------------------------------------------

m_pois <- glmmTMB(
  Count ~ Species + Zone + Trap_type + Silo +
    Temp_std + Hum_std +
    ns(Time_std, df = 3),
  data = df,
  family = poisson(link = "log")
)

pois_dispersion <- sum(
  residuals(m_pois, type = "pearson")^2,
  na.rm = TRUE
) / df.residual(m_pois)

# ------------------------------------------------------------
# 4.2 Negative binomial model
# ------------------------------------------------------------
m_nb <- glmmTMB(
  Count ~ Species + Zone + Trap_type + Silo +
    Temp_std + Hum_std +
    ns(Time_std, df = 3),
  data = df,
  family = nbinom2(link = "log")
)
# ------------------------------------------------------------
# 4.3 Negative binomial + Temperature × Grain Moisture
# ------------------------------------------------------------
m_nb_int <- glmmTMB(
  Count ~ Species + Zone + Trap_type + Silo +
    Temp_std * Hum_std +
    ns(Time_std, df = 3),
  data = df,
  family = nbinom2(link = "log")
)
# Test contribution of Temperature × Grain Moisture interaction
lrt_interaction <- anova(
  m_nb,
  m_nb_int
)
# ------------------------------------------------------------
# 4.4 Zero-inflated negative binomial model
# ------------------------------------------------------------

m_zinb <- glmmTMB(
  Count ~ Species + Zone + Trap_type + Silo +
    Temp_std * Hum_std +
    ns(Time_std, df = 3),
  
  ziformula = ~ Species + Trap_type + Silo +
    Temp_std + Hum_std + Time_std,
  
  data = df,
  family = nbinom2(link = "log")
)
# ------------------------------------------------------------
# ZINB without Temperature × Grain Moisture interaction
# ------------------------------------------------------------

m_zinb_add <- glmmTMB(
  Count ~ Species + Zone + Trap_type + Silo +
    Temp_std + Hum_std +
    ns(Time_std, df = 3),
  
  ziformula = ~ Species + Trap_type + Silo +
    Temp_std + Hum_std + Time_std,
  
  data = df,
  family = nbinom2(link = "log")
)


cat("\n=== Additive ZINB model ===\n")
cat(sprintf("AIC: %.2f\n", AIC(m_zinb_add)))
cat(sprintf("BIC: %.2f\n", BIC(m_zinb_add)))


# Compare additive and interaction ZINB models
lrt_zinb_interaction <- anova(
  m_zinb_add,
  m_zinb
)

cat("\n=== ZINB: additive vs Temperature × Grain Moisture interaction ===\n")
print(lrt_zinb_interaction)
# ------------------------------------------------------------
# 4.4.1 Numerical checks and zero-inflation sensitivity
# ------------------------------------------------------------

# Original additive ZINB: numerical diagnostics
cat("\n=== Original additive ZINB: convergence ===\n")
print(m_zinb_add$fit$convergence)
print(m_zinb_add$fit$message)
print(m_zinb_add$sdr$pdHess)

glmmTMB::diagnose(m_zinb_add)

cat("\n=== Original zero-inflation coefficients ===\n")
print(summary(m_zinb_add)$coefficients$zi)


# Sensitivity model:
# omit Species ONLY from the zero-inflation component.
# The conditional count component remains unchanged.
m_zinb_add_check <- update(
  m_zinb_add,
  ziformula = ~ Trap_type + Silo +
    Temp_std + Hum_std + Time_std
)

cat("\n=== Simplified zero-inflation model: convergence ===\n")
print(m_zinb_add_check$fit$convergence)
print(m_zinb_add_check$sdr$pdHess)

cat("\n=== Original vs simplified zero-inflation model ===\n")
print(AIC(m_zinb_add, m_zinb_add_check))

cat("\n=== Simplified zero-inflation coefficients ===\n")
print(summary(m_zinb_add_check)$coefficients$zi)


# ------------------------------------------------------------
# 4.4.2 BFGS refit initialized from original coefficients
# ------------------------------------------------------------

# Same model specification; alternative optimizer.
# Conditional and zero-inflation coefficients are initialized
# at the estimates from the original fit.
m_zinb_add_bfgs_start <- update(
  m_zinb_add,
  start = list(
    beta = unname(glmmTMB::fixef(m_zinb_add)$cond),
    betazi = unname(glmmTMB::fixef(m_zinb_add)$zi)
  ),
  control = glmmTMB::glmmTMBControl(
    optimizer = optim,
    optArgs = list(method = "BFGS")
  )
)

cat("\n=== BFGS refit: convergence ===\n")
print(m_zinb_add_bfgs_start$fit$convergence)
print(m_zinb_add_bfgs_start$sdr$pdHess)

cat("\n=== Negative log-likelihood comparison ===\n")
print(c(
  Original = m_zinb_add$fit$objective,
  BFGS_original_start = m_zinb_add_bfgs_start$fit$objective
))

cat("\n=== BFGS zero-inflation coefficients ===\n")
print(summary(m_zinb_add_bfgs_start)$coefficients$zi)


# Compare conditional environmental estimates and SE
cat("\n=== Environmental estimates: original model ===\n")
print(
  summary(m_zinb_add)$coefficients$cond[
    c("Temp_std", "Hum_std"), , drop = FALSE
  ]
)

cat("\n=== Environmental estimates: simplified ZI model ===\n")
print(
  summary(m_zinb_add_check)$coefficients$cond[
    c("Temp_std", "Hum_std"), , drop = FALSE
  ]
)

cat("\n=== Environmental estimates: BFGS refit ===\n")
print(
  summary(m_zinb_add_bfgs_start)$coefficients$cond[
    c("Temp_std", "Hum_std"), , drop = FALSE
  ]
)


# ------------------------------------------------------------
# 4.4.3 Group-level patterns relevant to ZI instability
# ------------------------------------------------------------

# Observed zeros and counts by silo and species
zi_observed_summary <- df %>%
  dplyr::group_by(Silo, Species) %>%
  dplyr::summarise(
    N = sum(!is.na(Count)),
    Zeros = sum(Count == 0, na.rm = TRUE),
    Zero_percent = 100 * Zeros / N,
    Mean_count = mean(Count, na.rm = TRUE),
    Max_count = max(Count, na.rm = TRUE),
    .groups = "drop"
  )

cat("\n=== Observed counts by silo and species ===\n")
print(zi_observed_summary, n = Inf, width = Inf)


# Positive O. surinamensis records in Silo 3
zi_positive_records <- df %>%
  dplyr::filter(
    Silo == "3",
    Species == "Oryzaephilus surinamensis",
    Count > 0
  ) %>%
  dplyr::select(
    Silo, Species, Zone, Trap_type,
    Time_std, Temp_std, Hum_std, Count
  )

cat("\n=== Positive O. surinamensis records in Silo 3 ===\n")
print(zi_positive_records, n = Inf, width = Inf)


# Fitted probability of the additional-zero component.
# This is NOT the total probability of observing a zero.
zi_prob <- predict(
  m_zinb_add,
  newdata = df,
  type = "zprob"
)

stopifnot(
  length(zi_prob) == nrow(df),
  all(is.finite(zi_prob))
)

zi_probability_summary <- df %>%
  dplyr::mutate(
    ZI_probability = as.numeric(zi_prob)
  ) %>%
  dplyr::group_by(Silo, Species) %>%
  dplyr::summarise(
    Min_ZI = min(ZI_probability),
    Median_ZI = median(ZI_probability),
    Max_ZI = max(ZI_probability),
    .groups = "drop"
  )

cat("\n=== Additional-zero probabilities by group ===\n")
print(zi_probability_summary, n = Inf, width = Inf)

# The original m_zinb_add object is retained unchanged.
# Sensitivity fits do not replace it in subsequent analyses.
# ------------------------------------------------------------
# 4.5 Sensitivity analysis: linear vs nonlinear time
# ------------------------------------------------------------

# Linear-time versions of the two principal models.
# All other model components are kept identical.

m_nb_int_linear <- glmmTMB(
  Count ~ Species + Zone + Trap_type + Silo +
    Temp_std * Hum_std +
    Time_std,
  data = df,
  family = nbinom2(link = "log")
)

m_zinb_linear <- glmmTMB(
  Count ~ Species + Zone + Trap_type + Silo +
    Temp_std * Hum_std +
    Time_std,
  
  ziformula = ~ Species + Trap_type + Silo +
    Temp_std + Hum_std + Time_std,
  
  data = df,
  family = nbinom2(link = "log")
)


# Compare temporal structures
time_structure_comparison <- data.frame(
  Model = c(
    "NB interaction - linear time",
    "NB interaction - spline time",
    "ZINB interaction - linear time",
    "ZINB interaction - spline time"
  ),
  AIC = c(
    AIC(m_nb_int_linear),
    AIC(m_nb_int),
    AIC(m_zinb_linear),
    AIC(m_zinb)
  ),
  BIC = c(
    BIC(m_nb_int_linear),
    BIC(m_nb_int),
    BIC(m_zinb_linear),
    BIC(m_zinb)
  )
) %>%
  dplyr::mutate(
    Delta_AIC = AIC - min(AIC),
    Delta_BIC = BIC - min(BIC)
  )

cat("\n=== Linear vs nonlinear temporal structure ===\n")
print(
  time_structure_comparison,
  row.names = FALSE
)


# Likelihood-ratio comparisons
lrt_time_nb <- anova(
  m_nb_int_linear,
  m_nb_int
)

lrt_time_zinb <- anova(
  m_zinb_linear,
  m_zinb
)

cat("\n=== NB: linear vs spline time ===\n")
print(lrt_time_nb)

cat("\n=== ZINB: linear vs spline time ===\n")
print(lrt_time_zinb)


write.csv(
  time_structure_comparison,
  "time_structure_comparison.csv",
  row.names = FALSE
)

# ------------------------------------------------------------
# 4.6 Model comparison
# ------------------------------------------------------------
aic_table <- data.frame(
  Model = c(
    "Poisson",
    "Negative binomial",
    "NB + Temperature x Grain Moisture",
    "ZINB",
    "ZINB + Temperature x Grain Moisture"
  ),
  AIC = c(
    AIC(m_pois),
    AIC(m_nb),
    AIC(m_nb_int),
    AIC(m_zinb_add),
    AIC(m_zinb)
  )
)

aic_table$Delta_AIC <-
  aic_table$AIC - min(aic_table$AIC)

aic_table <- aic_table[
  order(aic_table$AIC),
]
# ------------------------------------------------------------
# 4.7 Results
# ------------------------------------------------------------
cat("\n=== Poisson model ===\n")
cat(sprintf("AIC: %.2f\n", AIC(m_pois)))
cat(sprintf("Pearson dispersion: %.2f\n", pois_dispersion))

cat("\n=== Negative binomial model ===\n")
cat(sprintf("AIC: %.2f\n", AIC(m_nb)))

cat("\n=== NB + Temperature × Grain Moisture ===\n")
cat(sprintf("AIC: %.2f\n", AIC(m_nb_int)))

cat("\n=== Likelihood-ratio test: Temperature × Grain Moisture ===\n")
print(lrt_interaction)

cat("\n=== ZINB model ===\n")
cat(sprintf("AIC: %.2f\n", AIC(m_zinb)))
cat(sprintf("Log-likelihood: %.2f\n", as.numeric(logLik(m_zinb))))

cat("\n=== Frequentist model comparison ===\n")
print(aic_table, row.names = FALSE)

write.csv(
  aic_table,
  "frequentist_model_comparison.csv",
  row.names = FALSE
)
# -----------------------------------------------------------
# 4.8 ZINB coefficient summaries
# ------------------------------------------------------------

cat("\n=== ZINB: conditional count component ===\n")
print(summary(m_zinb)$coefficients$cond)

cat("\n=== ZINB: zero-inflation component ===\n")
print(summary(m_zinb)$coefficients$zi)


# ------------------------------------------------------------
# 4.9 Effect sizes for the final additive ZINB model
# ------------------------------------------------------------

zinb_conditional_coef <- summary(
  m_zinb_add
)$coefficients$cond


zinb_effect_sizes <- data.frame(
  Predictor = rownames(zinb_conditional_coef),
  Beta = zinb_conditional_coef[, "Estimate"],
  SE = zinb_conditional_coef[, "Std. Error"],
  z = zinb_conditional_coef[, "z value"],
  p_value = zinb_conditional_coef[, "Pr(>|z|)"],
  row.names = NULL
) %>%
  dplyr::mutate(
    IRR = exp(Beta),
    CI_95_Lower = exp(
      Beta - 1.96 * SE
    ),
    CI_95_Upper = exp(
      Beta + 1.96 * SE
    )
  )


# Spline basis coefficients are retained in the complete model
# output but are not interpreted individually as IRRs.

zinb_effect_sizes_report <- zinb_effect_sizes %>%
  dplyr::filter(
    Predictor != "(Intercept)",
    !grepl(
      "^ns\\(",
      Predictor
    )
  )


cat(
  "\n=== Final additive ZINB: effect sizes (IRR and 95% CI) ===\n"
)

print(
  zinb_effect_sizes_report,
  row.names = FALSE,
  digits = 4
)


write.csv(
  zinb_effect_sizes_report,
  "final_ZINB_effect_sizes.csv",
  row.names = FALSE
)
# ============================================================
# 5. MODEL DIAGNOSTICS
# ============================================================
# Diagnostics are evaluated for:
# 1. NB + Temperature × Grain Moisture interaction
# 2. ZINB + Temperature × Grain Moisture interaction
# ------------------------------------------------------------
# 5.1 DHARMa residual simulations
# ------------------------------------------------------------

set.seed(42)
sim_nb_int <- DHARMa::simulateResiduals(
  fittedModel = m_nb_int,
  n = 1000,
  plot = FALSE
)

set.seed(42)
sim_zinb <- DHARMa::simulateResiduals(
  fittedModel = m_zinb,
  n = 1000,
  plot = FALSE
)
# ------------------------------------------------------------
# 5.2 Diagnostic plots
# ------------------------------------------------------------

png(
  "NB_DHARMa_diagnostics.png",
  width = 1600,
  height = 1200
)
plot(sim_nb_int)
dev.off()

png(
  "ZINB_DHARMa_diagnostics.png",
  width = 1600,
  height = 1200
)
plot(sim_zinb)
dev.off()
# ------------------------------------------------------------
# 5.3 Standard DHARMa tests
# ------------------------------------------------------------

# NB
nb_uniformity <- DHARMa::testUniformity(sim_nb_int)
nb_dispersion <- DHARMa::testDispersion(sim_nb_int)
nb_zeros      <- DHARMa::testZeroInflation(sim_nb_int)

set.seed(42)
nb_outliers <- DHARMa::testOutliers(
  sim_nb_int,
  type = "bootstrap",
  nBoot = 1000
)

# ZINB
zinb_uniformity <- DHARMa::testUniformity(sim_zinb)
zinb_dispersion <- DHARMa::testDispersion(sim_zinb)
zinb_zeros      <- DHARMa::testZeroInflation(sim_zinb)

set.seed(42)
zinb_outliers <- DHARMa::testOutliers(
  sim_zinb,
  type = "bootstrap",
  nBoot = 1000
)
# ------------------------------------------------------------
# 5.4 Residual temporal dependence
# ------------------------------------------------------------

# Residuals are aggregated by sampling occasion.
# Sampling time is already represented by a natural cubic
# spline with 3 degrees of freedom in both models.

time_levels <- sort(unique(df$Time_Index))

time_group <- factor(
  df$Time_Index,
  levels = time_levels
)

# NB
sim_nb_time <- DHARMa::recalculateResiduals(
  sim_nb_int,
  group = time_group
)

nb_temporal <- DHARMa::testTemporalAutocorrelation(
  sim_nb_time,
  time = time_levels
)

# ZINB
sim_zinb_time <- DHARMa::recalculateResiduals(
  sim_zinb,
  group = time_group
)

zinb_temporal <- DHARMa::testTemporalAutocorrelation(
  sim_zinb_time,
  time = time_levels
)

set.seed(42)

sim_zinb_add <- DHARMa::simulateResiduals(
  fittedModel = m_zinb_add,
  n = 1000,
  plot = FALSE
)

zinb_add_uniformity <- DHARMa::testUniformity(sim_zinb_add)
zinb_add_dispersion <- DHARMa::testDispersion(sim_zinb_add)
zinb_add_zeros      <- DHARMa::testZeroInflation(sim_zinb_add)

set.seed(42)

zinb_add_outliers <- DHARMa::testOutliers(
  sim_zinb_add,
  type = "bootstrap",
  nBoot = 1000
)

sim_zinb_add_time <- DHARMa::recalculateResiduals(
  sim_zinb_add,
  group = time_group
)

zinb_add_temporal <- DHARMa::testTemporalAutocorrelation(
  sim_zinb_add_time,
  time = time_levels
)

cat("\n=== FINAL ADDITIVE ZINB DIAGNOSTICS ===\n")
print(zinb_add_uniformity)
print(zinb_add_dispersion)
print(zinb_add_zeros)
print(zinb_add_outliers)
print(zinb_add_temporal)
# ------------------------------------------------------------
# 5.5 Diagnostic results
# ------------------------------------------------------------

cat("\n=== NB diagnostics ===\n")
print(nb_uniformity)
print(nb_dispersion)
print(nb_zeros)
print(nb_outliers)
print(nb_temporal)
cat("\n=== ZINB diagnostics ===\n")
print(zinb_uniformity)
print(zinb_dispersion)
print(zinb_zeros)
print(zinb_outliers)
print(zinb_temporal)
# ------------------------------------------------------------
# 5.6 Diagnostic summary
# ------------------------------------------------------------
diagnostic_table <- data.frame(
  Model = c(
    "NB + Temperature x Grain Moisture",
    "ZINB + Temperature x Grain Moisture"
  ),
  Uniformity_p = c(
    nb_uniformity$p.value,
    zinb_uniformity$p.value
  ),
  Dispersion_p = c(
    nb_dispersion$p.value,
    zinb_dispersion$p.value
  ),
  Zero_inflation_p = c(
    nb_zeros$p.value,
    zinb_zeros$p.value
  ),
  Bootstrap_outlier_p = c(
    nb_outliers$p.value,
    zinb_outliers$p.value
  ),
  Temporal_DW = c(
    unname(nb_temporal$statistic),
    unname(zinb_temporal$statistic)
  ),
  Temporal_p = c(
    nb_temporal$p.value,
    zinb_temporal$p.value
  )
)
cat("\n=== Diagnostic summary ===\n")
print(diagnostic_table, row.names = FALSE)

write.csv(
  diagnostic_table,
  "frequentist_diagnostic_summary.csv",
  row.names = FALSE
)

# ============================================================
# 6. BAYESIAN HIERARCHICAL ABUNDANCE MODEL
# ============================================================

# Hum_std = grain moisture content (%)
# Time is modelled nonlinearly using a natural cubic spline
# with 3 degrees of freedom.

# ------------------------------------------------------------
# 6.1 Priors
# ------------------------------------------------------------

bayes_priors <- c(
  prior(normal(0, 1), class = "b"),
  prior(normal(0, 1), class = "Intercept"),
  prior(normal(0, 1), class = "sd")
)

# ------------------------------------------------------------
# 6.2 Model specification
# ------------------------------------------------------------

bayes_formula <- bf(
  Count ~
    Temp_std * Hum_std +
    ns(Time_std, df = 3) +
    (1 | Species) +
    (1 | Zone) +
    (1 | Trap_type) +
    (1 | Silo),
  family = negbinomial()
)

# ------------------------------------------------------------
# 6.3 Model fitting
# ------------------------------------------------------------

cat("\n=== Fitting Bayesian hierarchical NB abundance model ===\n")

m_bayes <- brm(
  formula = bayes_formula,
  data = df,
  prior = bayes_priors,
  chains = 4,
  iter = 2000,
  warmup = 1000,
  cores = 4,
  seed = 42,
  backend = "cmdstanr",
  control = list(
    adapt_delta = 0.9,
    max_treedepth = 12
  )
)

# ------------------------------------------------------------
# 6.4 Save model and summary
# ------------------------------------------------------------

saveRDS(
  m_bayes,
  "m_bayes_final.rds"
)

cat("\n=== Bayesian hierarchical NB model summary ===\n")
print(
  summary(m_bayes),
  digits = 3
)
# ============================================================
# 7. ENVIRONMENTAL INTERACTION FIGURE
# ============================================================

# Predictions are evaluated for the same reference conditions:
# Species   = Cryptolestes ferrugineus
# Zone      = CENTER
# Trap_type = Trap_2m
# Silo      = 1
# Time      = mean sampling time


# ------------------------------------------------------------
# 7.1 Environmental prediction grid
# ------------------------------------------------------------

temp_seq <- seq(
  min(df$Temperature, na.rm = TRUE),
  max(df$Temperature, na.rm = TRUE),
  length.out = 100
)

hum_seq <- seq(
  min(df$Humidity, na.rm = TRUE),
  max(df$Humidity, na.rm = TRUE),
  length.out = 100
)

environment_grid <- expand.grid(
  Temperature = temp_seq,
  Humidity = hum_seq
)

environment_grid <- environment_grid %>%
  mutate(
    Temp_std = (
      Temperature - mean(df$Temperature, na.rm = TRUE)
    ) / sd(df$Temperature, na.rm = TRUE),
    
    Hum_std = (
      Humidity - mean(df$Humidity, na.rm = TRUE)
    ) / sd(df$Humidity, na.rm = TRUE),
    
    Time_std = 0,
    
    Species = factor(
      "Cryptolestes ferrugineus",
      levels = levels(df$Species)
    ),
    
    Zone = factor(
      "CENTER",
      levels = levels(df$Zone)
    ),
    
    Trap_type = factor(
      "Trap_2m",
      levels = levels(df$Trap_type)
    ),
    
    Silo = factor(
      "1",
      levels = levels(df$Silo)
    )
  )


# ------------------------------------------------------------
# 7.2 Frequentist ZINB predictions
# ------------------------------------------------------------

environment_grid$Pred_Frequentist <- predict(
  m_zinb,
  newdata = environment_grid,
  type = "response"
)

p_freq_surface <- ggplot(
  environment_grid,
  aes(
    x = Temperature,
    y = Humidity,
    fill = Pred_Frequentist
  )
) +
  geom_tile() +
  geom_point(
    data = df,
    aes(
      x = Temperature,
      y = Humidity
    ),
    inherit.aes = FALSE,
    alpha = 0.4,
    size = 1.2
  ) +
  scale_fill_viridis_c() +
  labs(
    title = "ZINB: Temperature × Grain Moisture",
    x = "Grain temperature (°C)",
    y = "Grain moisture content (%)",
    fill = "Expected count"
  ) +
  theme_bw()


# ------------------------------------------------------------
# 7.3 Bayesian hierarchical NB predictions
# ------------------------------------------------------------

environment_grid$Pred_Bayes <- predict(
  m_bayes,
  newdata = environment_grid,
  re_formula = NULL
)[, "Estimate"]

p_bayes_surface <- ggplot(
  environment_grid,
  aes(
    x = Temperature,
    y = Humidity,
    fill = Pred_Bayes
  )
) +
  geom_tile() +
  geom_point(
    data = df,
    aes(
      x = Temperature,
      y = Humidity
    ),
    inherit.aes = FALSE,
    alpha = 0.4,
    size = 1.2
  ) +
  scale_fill_viridis_c() +
  labs(
    title = "Bayesian NB: Temperature × Grain Moisture",
    x = "Grain temperature (°C)",
    y = "Grain moisture content (%)",
    fill = "Expected count"
  ) +
  theme_bw()


# ------------------------------------------------------------
# 7.4 Frequentist interaction slices
# ------------------------------------------------------------

hum_levels_std <- c(-1, 0, 1)

hum_raw_levels <- (
  mean(df$Humidity, na.rm = TRUE) +
    hum_levels_std * sd(df$Humidity, na.rm = TRUE)
)

hum_labels <- c(
  sprintf("Low moisture (%.1f%%)", hum_raw_levels[1]),
  sprintf("Mean moisture (%.1f%%)", hum_raw_levels[2]),
  sprintf("High moisture (%.1f%%)", hum_raw_levels[3])
)

slice_data <- do.call(
  rbind,
  lapply(seq_along(hum_levels_std), function(i) {
    
    data.frame(
      Temperature = temp_seq,
      
      Temp_std = (
        temp_seq - mean(df$Temperature, na.rm = TRUE)
      ) / sd(df$Temperature, na.rm = TRUE),
      
      Hum_std = hum_levels_std[i],
      HumLevel = hum_labels[i],
      
      Time_std = 0,
      
      Species = factor(
        "Cryptolestes ferrugineus",
        levels = levels(df$Species)
      ),
      
      Zone = factor(
        "CENTER",
        levels = levels(df$Zone)
      ),
      
      Trap_type = factor(
        "Trap_2m",
        levels = levels(df$Trap_type)
      ),
      
      Silo = factor(
        "1",
        levels = levels(df$Silo)
      )
    )
  })
)

slice_data$Pred_Frequentist <- predict(
  m_zinb,
  newdata = slice_data,
  type = "response"
)

p_interaction_slices <- ggplot(
  slice_data,
  aes(
    x = Temperature,
    y = Pred_Frequentist,
    color = HumLevel
  )
) +
  geom_line(linewidth = 1.4) +
  labs(
    title = "Temperature effect at different grain moisture levels",
    x = "Grain temperature (°C)",
    y = "Expected count",
    color = "Grain moisture content"
  ) +
  theme_bw()


# ------------------------------------------------------------
# 7.5 Combine and save
# ------------------------------------------------------------

interaction_figure <- (
  p_freq_surface |
    p_bayes_surface |
    p_interaction_slices
)

ggsave(
  filename = "interaction_surface_figure.png",
  plot = interaction_figure,
  width = 16,
  height = 6,
  dpi = 300
)
# ============================================================
# 8. BAYESIAN MODEL DIAGNOSTICS
# ============================================================

color_scheme_set("mix-blue-red")


# ------------------------------------------------------------
# 8.1 Trace plots
# ------------------------------------------------------------

# Key environmental parameters are inspected visually.
# Convergence of all model parameters, including spline
# coefficients, is assessed from R-hat and ESS in the
# complete model summary.

p_trace <- mcmc_trace(
  m_bayes,
  pars = c(
    "b_Intercept",
    "b_Temp_std",
    "b_Hum_std",
    "b_Temp_std:Hum_std"
  )
)


# ------------------------------------------------------------
# 8.2 Environmental-effect posterior distributions
# ------------------------------------------------------------

p_areas <- mcmc_areas(
  m_bayes,
  pars = c(
    "b_Temp_std",
    "b_Hum_std",
    "b_Temp_std:Hum_std"
  ),
  prob = 0.95
) +
  geom_vline(
    xintercept = 0,
    linetype = "dashed"
  ) +
  ggtitle(
    "Environmental Effects: 95% Credible Intervals"
  )


# ------------------------------------------------------------
# 8.3 Posterior predictive check
# ------------------------------------------------------------

p_ppc <- pp_check(
  m_bayes,
  ndraws = 50,
  type = "hist"
) +
  coord_cartesian(
    xlim = c(0, 50)
  ) +
  ggtitle(
    "Posterior Predictive Check"
  )


# ------------------------------------------------------------
# 8.4 Group-level standard deviations
# ------------------------------------------------------------

p_group_sd <- mcmc_intervals(
  m_bayes,
  pars = c(
    "sd_Species__Intercept",
    "sd_Zone__Intercept",
    "sd_Trap_type__Intercept",
    "sd_Silo__Intercept"
  ),
  prob = 0.95
) +
  ggtitle(
    "Group-Level Variation"
  )


# ------------------------------------------------------------
# 8.5 Combined diagnostic figure
# ------------------------------------------------------------

bayesian_diagnostics <- (
  p_trace | p_areas
) / (
  p_ppc | p_group_sd
)

ggsave(
  filename = "bayesian_summary.png",
  plot = bayesian_diagnostics,
  width = 16,
  height = 10,
  dpi = 150
)
# ============================================================
# 9. BAYESIAN POSTERIOR SUMMARY FIGURE
# ============================================================

# Posterior draws are required for the negative-binomial
# shape-parameter distribution.

post <- as.data.frame(m_bayes)


# ------------------------------------------------------------
# 9.1 Environmental effects
# ------------------------------------------------------------

p_fixed <- p_areas +
  ggtitle(
    "Environmental Effects Posterior Distributions"
  )


# ------------------------------------------------------------
# 9.2 Group-level variation
# ------------------------------------------------------------

p_groups <- p_group_sd +
  ggtitle(
    "Group-Level Variation"
  )


# ------------------------------------------------------------
# 9.3 Negative-binomial shape parameter
# ------------------------------------------------------------

p_shape <- ggplot(
  post,
  aes(x = shape)
) +
  geom_density(
    fill = "grey70",
    alpha = 0.7
  ) +
  geom_vline(
    xintercept = mean(post$shape),
    linetype = "dashed"
  ) +
  labs(
    title = "Negative-Binomial Shape Parameter",
    x = "Shape parameter",
    y = "Posterior density"
  ) +
  theme_minimal()


# ------------------------------------------------------------
# 9.4 Combine and save
# ------------------------------------------------------------

bayesian_posterior_figure <- (
  p_fixed |
    p_groups |
    p_shape
)

ggsave(
  filename = "Figure4_BayesianPosterior.png",
  plot = bayesian_posterior_figure,
  width = 14,
  height = 5,
  dpi = 300
)
# ============================================================
# 10. BAYESIAN GROUP-LEVEL EFFECTS
# ============================================================

# Posterior means and 95% credible intervals for the
# group-level intercepts of Species, Zone, Trap_type and Silo.


# ------------------------------------------------------------
# 10.1 Plotting function
# ------------------------------------------------------------

plot_random_effects <- function(
    model,
    group_name,
    main_title
) {
  
  re <- ranef(model)[[group_name]][, , "Intercept"]
  
  means  <- re[, "Estimate"]
  lower  <- re[, "Q2.5"]
  upper  <- re[, "Q97.5"]
  labels <- rownames(re)
  
  y_pos <- seq_along(labels)
  
  plot(
    means,
    y_pos,
    xlim = range(c(lower, upper)),
    yaxt = "n",
    pch = 16,
    xlab = "Group-level effect (log scale)",
    ylab = "",
    main = main_title
  )
  
  segments(
    lower,
    y_pos,
    upper,
    y_pos,
    lwd = 1.5
  )
  
  abline(
    v = 0,
    lty = 2,
    col = "gray"
  )
  
  axis(
    2,
    at = y_pos,
    labels = labels,
    las = 1,
    cex.axis = 0.9
  )
}
# ------------------------------------------------------------
# 10.2 Group-level effect figure
# ------------------------------------------------------------
png(
  "bayesian_random_effects.png",
  width = 14,
  height = 10,
  units = "in",
  res = 200
)

par(
  mfrow = c(2, 2),
  mar = c(5, 14, 4, 2)
)

plot_random_effects(
  m_bayes,
  "Species",
  "Species Effects"
)

plot_random_effects(
  m_bayes,
  "Zone",
  "Zone Effects"
)

plot_random_effects(
  m_bayes,
  "Trap_type",
  "Sampling Category Effects"
)

plot_random_effects(
  m_bayes,
  "Silo",
  "Silo Effects"
)

dev.off()
# ============================================================
# 11. NONLINEAR TEMPORAL MODELS: NATURAL CUBIC SPLINES
# ============================================================

# Species-specific temporal trajectories are modelled using
# natural cubic splines.
#
# Models are adjusted for sampling category, grain temperature
# and grain moisture content, with random intercepts for Silo
# and Zone nested within Silo.


# ------------------------------------------------------------
# 11.1 Full-data spline models
# ------------------------------------------------------------

mSpline_df3 <- glmmTMB(
  Count ~
    Species * ns(Time_std, df = 3) +
    Trap_type +
    Temp_std +
    Hum_std +
    (1 | Silo/Zone),
  data = df,
  family = nbinom2()
)

mSpline_df4 <- glmmTMB(
  Count ~
    Species * ns(Time_std, df = 4) +
    Trap_type +
    Temp_std +
    Hum_std +
    (1 | Silo/Zone),
  data = df,
  family = nbinom2()
)


# ------------------------------------------------------------
# 11.2 Model comparison: df = 3 vs df = 4
# ------------------------------------------------------------

spline_models <- list(
  "Spline df = 3" = mSpline_df3,
  "Spline df = 4" = mSpline_df4
)

spline_model_comparison <- data.frame(
  Model = names(spline_models),
  AIC = sapply(spline_models, AIC),
  BIC = sapply(spline_models, BIC)
)

spline_model_comparison <- spline_model_comparison[
  order(spline_model_comparison$AIC),
]

cat("\n=== Spline model comparison ===\n")
print(
  spline_model_comparison,
  row.names = FALSE
)

write.csv(
  spline_model_comparison,
  "spline_model_comparison.csv",
  row.names = FALSE
)


# ------------------------------------------------------------
# 11.3 DHARMa diagnostics
# ------------------------------------------------------------

set.seed(42)
sim_df3 <- DHARMa::simulateResiduals(
  fittedModel = mSpline_df3,
  n = 1000,
  plot = FALSE
)

set.seed(42)
sim_df4 <- DHARMa::simulateResiduals(
  fittedModel = mSpline_df4,
  n = 1000,
  plot = FALSE
)


# Diagnostic plots

png(
  "DHARMa_spline_df3.png",
  width = 1600,
  height = 1200
)
plot(sim_df3)
dev.off()

png(
  "DHARMa_spline_df4.png",
  width = 1600,
  height = 1200
)
plot(sim_df4)
dev.off()


# Formal DHARMa tests: df = 3

df3_uniformity <- DHARMa::testUniformity(sim_df3)
df3_dispersion <- DHARMa::testDispersion(sim_df3)
df3_zeros      <- DHARMa::testZeroInflation(sim_df3)

set.seed(42)
df3_outliers <- DHARMa::testOutliers(
  sim_df3,
  type = "bootstrap",
  nBoot = 1000
)


# Formal DHARMa tests: df = 4

df4_uniformity <- DHARMa::testUniformity(sim_df4)
df4_dispersion <- DHARMa::testDispersion(sim_df4)
df4_zeros      <- DHARMa::testZeroInflation(sim_df4)

set.seed(42)
df4_outliers <- DHARMa::testOutliers(
  sim_df4,
  type = "bootstrap",
  nBoot = 1000
)


cat("\n=== Spline df = 3 diagnostics ===\n")
print(df3_uniformity)
print(df3_dispersion)
print(df3_zeros)
print(df3_outliers)

cat("\n=== Spline df = 4 diagnostics ===\n")
print(df4_uniformity)
print(df4_dispersion)
print(df4_zeros)
print(df4_outliers)


# ------------------------------------------------------------
# 11.4 Species-specific temporal predictions
# ------------------------------------------------------------

# Predictions are evaluated for:
# - Trap_2m
# - mean grain temperature (Temp_std = 0)
# - mean grain moisture content (Hum_std = 0)
# - population-level random effects

spline_grid <- expand.grid(
  Time_std = seq(
    min(df$Time_std, na.rm = TRUE),
    max(df$Time_std, na.rm = TRUE),
    length.out = 500
  ),
  Species = levels(df$Species),
  Trap_type = "Trap_2m",
  Temp_std = 0,
  Hum_std = 0,
  Silo = levels(df$Silo)[1],
  Zone = levels(df$Zone)[1]
)

spline_grid$Species <- factor(
  spline_grid$Species,
  levels = levels(df$Species)
)

spline_grid$Trap_type <- factor(
  spline_grid$Trap_type,
  levels = levels(df$Trap_type)
)

spline_grid$Silo <- factor(
  spline_grid$Silo,
  levels = levels(df$Silo)
)

spline_grid$Zone <- factor(
  spline_grid$Zone,
  levels = levels(df$Zone)
)


# Convert standardized time back to sampling-occasion scale

time_index_mean <- mean(
  df$Time_Index,
  na.rm = TRUE
)

time_index_sd <- sd(
  df$Time_Index,
  na.rm = TRUE
)

spline_grid$Time_Index <- (
  spline_grid$Time_std * time_index_sd +
    time_index_mean
)


# Population-level predictions

spline_grid$fit_df3 <- predict(
  mSpline_df3,
  newdata = spline_grid,
  type = "response",
  re.form = NA,
  allow.new.levels = TRUE
)

spline_grid$fit_df4 <- predict(
  mSpline_df4,
  newdata = spline_grid,
  type = "response",
  re.form = NA,
  allow.new.levels = TRUE
)


# ------------------------------------------------------------
# 11.5 Raw means for visual comparison
# ------------------------------------------------------------

# Predictions use Trap_2m as the reference sampling category;
# therefore the raw-data overlay also uses Trap_2m observations.

raw_spline_means <- df %>%
  dplyr::filter(
    Trap_type == "Trap_2m"
  ) %>%
  dplyr::group_by(
    Species,
    Time_Index
  ) %>%
  dplyr::summarise(
    Mean_Count = mean(
      Count,
      na.rm = TRUE
    ),
    .groups = "drop"
  )


# ------------------------------------------------------------
# 11.6 Species-specific spline trajectories
# ------------------------------------------------------------

p_spline <- ggplot() +
  
  geom_point(
    data = raw_spline_means,
    aes(
      x = Time_Index,
      y = Mean_Count
    ),
    alpha = 0.4,
    size = 1.5
  ) +
  
  geom_line(
    data = spline_grid,
    aes(
      x = Time_Index,
      y = fit_df3,
      color = "Spline df = 3"
    ),
    linewidth = 1.1
  ) +
  
  geom_line(
    data = spline_grid,
    aes(
      x = Time_Index,
      y = fit_df4,
      color = "Spline df = 4"
    ),
    linewidth = 1.1,
    linetype = "dashed"
  ) +
  
  facet_wrap(
    ~ Species,
    scales = "free_y"
  ) +
  
  scale_x_continuous(
    breaks = seq(
      min(df$Time_Index),
      max(df$Time_Index),
      by = 2
    )
  ) +
  
  labs(
    x = "Sampling occasion",
    y = "Expected insect count",
    color = "Model",
    title = "Species-specific temporal trajectories"
  ) +
  
  theme_bw(
    base_size = 14
  ) +
  
  theme(
    legend.position = "bottom"
  )

ggsave(
  filename = "Spline_Figure.png",
  plot = p_spline,
  width = 14,
  height = 8,
  dpi = 300
)


# ------------------------------------------------------------
# 11.7 Sensitivity analysis: exclusion of grain-trier data
# ------------------------------------------------------------

df_probe <- df %>%
  dplyr::filter(
    Trap_type != "Trier"
  ) %>%
  droplevels()


# Same model specifications as the full-data models.
# The only difference is exclusion of Trier observations.

mSpline_df3_probe <- glmmTMB(
  Count ~
    Species * ns(Time_std, df = 3) +
    Trap_type +
    Temp_std +
    Hum_std +
    (1 | Silo/Zone),
  data = df_probe,
  family = nbinom2()
)

mSpline_df4_probe <- glmmTMB(
  Count ~
    Species * ns(Time_std, df = 4) +
    Trap_type +
    Temp_std +
    Hum_std +
    (1 | Silo/Zone),
  data = df_probe,
  family = nbinom2()
)


probe_model_comparison <- data.frame(
  Model = c(
    "Probe only: spline df = 3",
    "Probe only: spline df = 4"
  ),
  AIC = c(
    AIC(mSpline_df3_probe),
    AIC(mSpline_df4_probe)
  ),
  BIC = c(
    BIC(mSpline_df3_probe),
    BIC(mSpline_df4_probe)
  )
)

cat("\n=== Probe-only spline model comparison ===\n")
print(
  probe_model_comparison,
  row.names = FALSE
)

write.csv(
  probe_model_comparison,
  "probe_only_spline_model_comparison.csv",
  row.names = FALSE
)


# ------------------------------------------------------------
# 11.8 Function for species-specific peak timing
# ------------------------------------------------------------

get_peak_times <- function(
    model,
    data_ref,
    label
) {
  
  nd <- expand.grid(
    Time_std = seq(
      min(data_ref$Time_std, na.rm = TRUE),
      max(data_ref$Time_std, na.rm = TRUE),
      length.out = 500
    ),
    Species = levels(data_ref$Species),
    Trap_type = "Trap_2m",
    Temp_std = 0,
    Hum_std = 0,
    Silo = levels(data_ref$Silo)[1],
    Zone = levels(data_ref$Zone)[1]
  )
  
  nd$Species <- factor(
    nd$Species,
    levels = levels(data_ref$Species)
  )
  
  nd$Trap_type <- factor(
    nd$Trap_type,
    levels = levels(data_ref$Trap_type)
  )
  
  nd$Silo <- factor(
    nd$Silo,
    levels = levels(data_ref$Silo)
  )
  
  nd$Zone <- factor(
    nd$Zone,
    levels = levels(data_ref$Zone)
  )
  
  nd$Predicted_Count <- predict(
    model,
    newdata = nd,
    type = "response",
    re.form = NA,
    allow.new.levels = TRUE
  )
  
  nd %>%
    dplyr::group_by(
      Species
    ) %>%
    dplyr::slice_max(
      Predicted_Count,
      n = 1,
      with_ties = FALSE
    ) %>%
    dplyr::transmute(
      Species,
      Analysis = label,
      Peak_Time_std = Time_std,
      
      Peak_Time_Index =
        Time_std * time_index_sd +
        time_index_mean,
      
      Predicted_Peak = Predicted_Count
    )
}


# ------------------------------------------------------------
# 11.9 Peak-timing sensitivity analysis
# ------------------------------------------------------------

# df = 3

peak_full_df3 <- get_peak_times(
  model = mSpline_df3,
  data_ref = df,
  label = "All data"
)

peak_probe_df3 <- get_peak_times(
  model = mSpline_df3_probe,
  data_ref = df_probe,
  label = "Probe traps only"
)

peak_comparison_df3 <- dplyr::bind_rows(
  peak_full_df3,
  peak_probe_df3
)


# df = 4

peak_full_df4 <- get_peak_times(
  model = mSpline_df4,
  data_ref = df,
  label = "All data"
)

peak_probe_df4 <- get_peak_times(
  model = mSpline_df4_probe,
  data_ref = df_probe,
  label = "Probe traps only"
)

peak_comparison_df4 <- dplyr::bind_rows(
  peak_full_df4,
  peak_probe_df4
)


# ------------------------------------------------------------
# 11.10 Full-data vs probe-only peak comparison
# ------------------------------------------------------------

peak_table_df3 <- peak_full_df3 %>%
  dplyr::select(
    Species,
    Peak_All = Peak_Time_Index,
    Peak_Count_All = Predicted_Peak
  ) %>%
  dplyr::left_join(
    peak_probe_df3 %>%
      dplyr::select(
        Species,
        Peak_Probe = Peak_Time_Index,
        Peak_Count_Probe = Predicted_Peak
      ),
    by = "Species"
  ) %>%
  dplyr::mutate(
    Difference_in_peak_time =
      Peak_Probe - Peak_All
  )


peak_table_df4 <- peak_full_df4 %>%
  dplyr::select(
    Species,
    Peak_All_df4 = Peak_Time_Index,
    Peak_Count_All_df4 = Predicted_Peak
  ) %>%
  dplyr::left_join(
    peak_probe_df4 %>%
      dplyr::select(
        Species,
        Peak_Probe_df4 = Peak_Time_Index,
        Peak_Count_Probe_df4 = Predicted_Peak
      ),
    by = "Species"
  ) %>%
  dplyr::mutate(
    Difference_in_peak_time_df4 =
      Peak_Probe_df4 - Peak_All_df4
  )


# ------------------------------------------------------------
# 11.11 df = 3 vs df = 4 peak comparison
# ------------------------------------------------------------

df3_vs_df4 <- peak_full_df3 %>%
  dplyr::select(
    Species,
    Peak_df3 = Peak_Time_Index
  ) %>%
  dplyr::left_join(
    peak_full_df4 %>%
      dplyr::select(
        Species,
        Peak_df4 = Peak_Time_Index
      ),
    by = "Species"
  ) %>%
  dplyr::mutate(
    Difference_df4_minus_df3 =
      Peak_df4 - Peak_df3
  )


cat("\n=== Peak timing: df = 3 ===\n")
print(
  peak_table_df3,
  n = Inf,
  width = Inf
)

cat("\n=== Peak timing: df = 4 ===\n")
print(
  peak_table_df4,
  n = Inf,
  width = Inf
)

cat("\n=== Peak timing: df = 3 vs df = 4 ===\n")
print(
  df3_vs_df4,
  n = Inf,
  width = Inf
)


# ------------------------------------------------------------
# 11.12 Save peak-timing results
# ------------------------------------------------------------

write.csv(
  peak_comparison_df3,
  "spline_peak_sensitivity_df3.csv",
  row.names = FALSE
)

write.csv(
  peak_comparison_df4,
  "spline_peak_sensitivity_df4.csv",
  row.names = FALSE
)

write.csv(
  peak_table_df3,
  "spline_peak_comparison_df3.csv",
  row.names = FALSE
)

write.csv(
  peak_table_df4,
  "spline_peak_comparison_df4.csv",
  row.names = FALSE
)

write.csv(
  df3_vs_df4,
  "spline_peak_df3_vs_df4.csv",
  row.names = FALSE
)
# ============================================================
# 12. BAYESIAN DERIVATIVE-GOMPERTZ MODEL
# ============================================================

# The fitted nonlinear negative-binomial model is loaded from
# the saved final brms object.
#
# Model structure:
#
# log(mu) =
#   logA + logr -
#   exp(logr) * (Time_std - t0) -
#   exp(-exp(logr) * (Time_std - t0))
#
# with:
#
# logA ~ 1 + Species + Trap_type +
#        Temp_std * Hum_std +
#        (1 | Silo) + (1 | Zone)
#
# logr ~ 1 + Species
# t0   ~ 1 + Species
#
# The expected abundance reaches its maximum at t = t0.


# ------------------------------------------------------------
# 12.1 Load final Gompertz model
# ------------------------------------------------------------

fit_gomp <- readRDS(
  "fit_gompertz_final.rds"
)

cat("\n=== Bayesian derivative-Gompertz model summary ===\n")
print(
  summary(fit_gomp),
  digits = 3
)


# ------------------------------------------------------------
# 12.2 Extract species-specific posterior peak timing
# ------------------------------------------------------------

# One reference row for each species.
# Only Species enters the t0 submodel, but valid values for
# the remaining model variables are supplied for prediction.

peak_newdata <- data.frame(
  Species = factor(
    levels(df$Species),
    levels = levels(df$Species)
  ),
  
  Trap_type = factor(
    rep("Trap_2m", length(levels(df$Species))),
    levels = levels(df$Trap_type)
  ),
  
  Temp_std = 0,
  Hum_std = 0,
  Time_std = 0,
  
  Silo = factor(
    rep(levels(df$Silo)[1], length(levels(df$Species))),
    levels = levels(df$Silo)
  ),
  
  Zone = factor(
    rep(levels(df$Zone)[1], length(levels(df$Species))),
    levels = levels(df$Zone)
  )
)


# Posterior draws of t0.
# Because the derivative-Gompertz curve peaks exactly at t0,
# these draws are posterior draws of peak timing.

t0_draw_matrix <- brms::posterior_linpred(
  fit_gomp,
  newdata = peak_newdata,
  nlpar = "t0",
  re_formula = NA,
  transform = TRUE
)

colnames(t0_draw_matrix) <- as.character(
  peak_newdata$Species
)


peak_draws <- as.data.frame(
  t0_draw_matrix
) %>%
  dplyr::mutate(
    .draw = dplyr::row_number()
  ) %>%
  tidyr::pivot_longer(
    cols = -.draw,
    names_to = "Species",
    values_to = "Peak_Time_std"
  )


# ------------------------------------------------------------
# 12.3 Convert peak timing to sampling occasion and date
# ------------------------------------------------------------

time_index_mean <- mean(
  df$Time_Index,
  na.rm = TRUE
)

time_index_sd <- sd(
  df$Time_Index,
  na.rm = TRUE
)

peak_draws <- peak_draws %>%
  dplyr::mutate(
    Peak_Time_Index =
      Peak_Time_std * time_index_sd +
      time_index_mean
  )


# Date associated with each sampling occasion

time_date_key <- df %>%
  dplyr::distinct(
    Time_Index,
    Date_fixed
  ) %>%
  dplyr::arrange(
    Time_Index
  )


# Linear interpolation allows posterior peak estimates to fall
# between two observed sampling occasions.

peak_draws$Peak_Date_numeric <- approx(
  x = time_date_key$Time_Index,
  y = as.numeric(time_date_key$Date_fixed),
  xout = peak_draws$Peak_Time_Index,
  rule = 2
)$y


# ------------------------------------------------------------
# 12.4 Species-specific posterior peak summaries
# ------------------------------------------------------------

gompertz_peak_table <- peak_draws %>%
  dplyr::group_by(
    Species
  ) %>%
  dplyr::summarise(
    
    Peak_Index_Lower =
      as.numeric(
        quantile(
          Peak_Time_Index,
          0.025,
          na.rm = TRUE
        )
      ),
    
    Peak_Index_Median =
      median(
        Peak_Time_Index,
        na.rm = TRUE
      ),
    
    Peak_Index_Upper =
      as.numeric(
        quantile(
          Peak_Time_Index,
          0.975,
          na.rm = TRUE
        )
      ),
    
    Peak_Date_Num_Lower =
      as.numeric(
        quantile(
          Peak_Date_numeric,
          0.025,
          na.rm = TRUE
        )
      ),
    
    Peak_Date_Num_Median =
      median(
        Peak_Date_numeric,
        na.rm = TRUE
      ),
    
    Peak_Date_Num_Upper =
      as.numeric(
        quantile(
          Peak_Date_numeric,
          0.975,
          na.rm = TRUE
        )
      ),
    
    .groups = "drop"
  ) %>%
  
  dplyr::mutate(
    
    Peak_Date = as.Date(
      round(Peak_Date_Num_Median),
      origin = "1970-01-01"
    ),
    
    Peak_Date_Lower = as.Date(
      round(Peak_Date_Num_Lower),
      origin = "1970-01-01"
    ),
    
    Peak_Date_Upper = as.Date(
      round(Peak_Date_Num_Upper),
      origin = "1970-01-01"
    )
  ) %>%
  
  dplyr::transmute(
    Species,
    Peak_Time_Index = Peak_Index_Median,
    Peak_Time_Index_Lower = Peak_Index_Lower,
    Peak_Time_Index_Upper = Peak_Index_Upper,
    Peak_Date,
    Peak_Date_Lower,
    Peak_Date_Upper
  )


cat(
  "\n=== Gompertz species-specific peak timing ===\n"
)

print(
  gompertz_peak_table,
  n = Inf,
  width = Inf
)

write.csv(
  gompertz_peak_table,
  "gompertz_species_peak_timing.csv",
  row.names = FALSE
)


# ------------------------------------------------------------
# 12.5 Posterior fitted temporal curves
# ------------------------------------------------------------

time_grid <- seq(
  min(df$Time_Index, na.rm = TRUE),
  max(df$Time_Index, na.rm = TRUE),
  length.out = 300
)

gomp_grid <- expand.grid(
  Time_Index = time_grid,
  Species = levels(df$Species)
)

gomp_grid$Time_std <- (
  gomp_grid$Time_Index -
    time_index_mean
) / time_index_sd

gomp_grid$Temp_std <- 0
gomp_grid$Hum_std <- 0

gomp_grid$Trap_type <- factor(
  "Trap_2m",
  levels = levels(df$Trap_type)
)

# Valid placeholders for variables appearing in random effects.
# Group-level effects are excluded using re_formula = NA.

gomp_grid$Silo <- factor(
  levels(df$Silo)[1],
  levels = levels(df$Silo)
)

gomp_grid$Zone <- factor(
  levels(df$Zone)[1],
  levels = levels(df$Zone)
)

gomp_grid$Species <- factor(
  gomp_grid$Species,
  levels = levels(df$Species)
)


gomp_fit <- fitted(
  fit_gomp,
  newdata = gomp_grid,
  re_formula = NA,
  probs = c(0.025, 0.975)
)

gomp_grid$Estimate <- gomp_fit[, "Estimate"]
gomp_grid$Lower <- gomp_fit[, "Q2.5"]
gomp_grid$Upper <- gomp_fit[, "Q97.5"]


# ------------------------------------------------------------
# 12.6 Raw means for visual comparison
# ------------------------------------------------------------

raw_means_gomp <- df %>%
  dplyr::filter(
    Trap_type == "Trap_2m"
  ) %>%
  dplyr::group_by(
    Species,
    Time_Index
  ) %>%
  dplyr::summarise(
    Mean_Count = mean(
      Count,
      na.rm = TRUE
    ),
    .groups = "drop"
  )


gompertz_peak_plot <- gompertz_peak_table %>%
  dplyr::mutate(
    Species = factor(
      Species,
      levels = levels(df$Species)
    )
  )


# ------------------------------------------------------------
# 12.7 Gompertz fitted-curve figure
# ------------------------------------------------------------

species_labels <- c(
  "Cryptolestes ferrugineus" =
    "Cryptolestes\nferrugineus",
  
  "Oryzaephilus surinamensis" =
    "Oryzaephilus\nsurinamensis",
  
  "Rhyzopertha dominica" =
    "Rhyzopertha\ndominica",
  
  "Sitophilus oryzae" =
    "Sitophilus\noryzae",
  
  "Tribolium castaneum" =
    "Tribolium\ncastaneum"
)


p_gomp <- ggplot(
  gomp_grid,
  aes(
    x = Time_Index,
    y = Estimate
  )
) +
  
  geom_ribbon(
    aes(
      ymin = Lower,
      ymax = Upper
    ),
    alpha = 0.20
  ) +
  
  geom_point(
    data = raw_means_gomp,
    aes(
      x = Time_Index,
      y = Mean_Count
    ),
    inherit.aes = FALSE,
    alpha = 0.55,
    size = 2
  ) +
  
  geom_line(
    linewidth = 1.1
  ) +
  
  geom_vline(
    data = gompertz_peak_plot,
    aes(
      xintercept = Peak_Time_Index
    ),
    inherit.aes = FALSE,
    linetype = "dashed",
    linewidth = 0.7
  ) +
  
  facet_wrap(
    ~ Species,
    scales = "free_y",
    ncol = 3,
    labeller = as_labeller(
      species_labels
    )
  ) +
  
  scale_x_continuous(
    breaks = seq(
      1,
      15,
      by = 2
    ),
    limits = c(1, 15)
  ) +
  
  labs(
    x = "Sampling occasion",
    y = "Expected insect count"
  ) +
  
  theme_bw(
    base_size = 13
  ) +
  
  theme(
    strip.text = element_text(
      face = "italic",
      size = 10,
      lineheight = 0.95
    ),
    
    strip.background = element_rect(
      fill = "grey90"
    ),
    
    axis.text.x = element_text(
      size = 9
    ),
    
    panel.grid.minor = element_blank(),
    
    panel.spacing = grid::unit(
      1,
      "lines"
    )
  )


ggsave(
  filename = "Gompertz_species_specific_curves.png",
  plot = p_gomp,
  width = 14,
  height = 9,
  dpi = 300
)


# ------------------------------------------------------------
# 12.8 Gompertz vs primary spline df = 4
# ------------------------------------------------------------

spline_df4_peak_compare <- peak_table_df4 %>%
  dplyr::transmute(
    Species = as.character(
      Species
    ),
    Spline_df4_Peak_Time_Index =
      Peak_All_df4
  )


gompertz_vs_primary_spline <- gompertz_peak_table %>%
  dplyr::transmute(
    Species = as.character(
      Species
    ),
    Gompertz_Peak_Time_Index =
      Peak_Time_Index,
    Gompertz_Lower =
      Peak_Time_Index_Lower,
    Gompertz_Upper =
      Peak_Time_Index_Upper
  ) %>%
  
  dplyr::left_join(
    spline_df4_peak_compare,
    by = "Species"
  ) %>%
  
  dplyr::mutate(
    
    Difference_Time_Index =
      Gompertz_Peak_Time_Index -
      Spline_df4_Peak_Time_Index,
    
    Difference_Days =
      Difference_Time_Index * 15,
    
    Absolute_Difference_Days =
      abs(
        Difference_Days
      ),
    
    Spline_df4_within_Gompertz_95CrI =
      Spline_df4_Peak_Time_Index >=
      Gompertz_Lower &
      Spline_df4_Peak_Time_Index <=
      Gompertz_Upper
  )


cat(
  "\n=== Gompertz vs primary spline df = 4 ===\n"
)

print(
  gompertz_vs_primary_spline,
  n = Inf,
  width = Inf
)

write.csv(
  gompertz_vs_primary_spline,
  "gompertz_vs_primary_spline_df4.csv",
  row.names = FALSE
)
# ============================================================
# 13. FUMIGATION-THRESHOLD DETECTION ANALYSIS
# ============================================================

# The management threshold is defined using grain-trier density.
# Trier observations are used only to define the reference outcome
# and are not used as predictors.
#
# The threshold of 2 live insects/kg is a literature-based
# management reference, not a local regulatory threshold.


# ------------------------------------------------------------
# 13.1 Literature-based action threshold
# ------------------------------------------------------------

action_threshold_per_kg <- 2


# ------------------------------------------------------------
# 13.2 Sampled wheat mass represented by Trier observations
# ------------------------------------------------------------

# Each grain-trier sample represents 0.75 kg wheat:
# CENTER: 2 samples -> 1.50 kg
# MIDDLE: 5 samples -> 3.75 kg
# EDGE:   7 samples -> 5.25 kg

zone_sampling_mass <- data.frame(
  Zone = c(
    "CENTER",
    "MIDDLE",
    "EDGE"
  ),
  Trier_Samples = c(
    2,
    5,
    7
  ),
  Trier_Sampled_kg = c(
    1.50,
    3.75,
    5.25
  )
)


# ------------------------------------------------------------
# 13.3 Check environmental consistency within sampling units
# ------------------------------------------------------------

environmental_check <- df %>%
  dplyr::group_by(
    Date_fixed,
    Time_Index,
    Silo,
    Zone
  ) %>%
  dplyr::summarise(
    Temperature_Min = min(
      Temperature,
      na.rm = TRUE
    ),
    Temperature_Max = max(
      Temperature,
      na.rm = TRUE
    ),
    Moisture_Min = min(
      Humidity,
      na.rm = TRUE
    ),
    Moisture_Max = max(
      Humidity,
      na.rm = TRUE
    ),
    Temperature_Range =
      Temperature_Max - Temperature_Min,
    Moisture_Range =
      Moisture_Max - Moisture_Min,
    .groups = "drop"
  )

cat("\nMaximum within-unit temperature range:\n")
print(
  max(
    environmental_check$Temperature_Range,
    na.rm = TRUE
  )
)

cat("\nMaximum within-unit grain moisture range:\n")
print(
  max(
    environmental_check$Moisture_Range,
    na.rm = TRUE
  )
)


# ------------------------------------------------------------
# 13.4 Environmental information by sampling unit
# ------------------------------------------------------------

environmental_data <- df %>%
  dplyr::group_by(
    Date_fixed,
    Time_Index,
    Silo,
    Zone
  ) %>%
  dplyr::summarise(
    Temperature = mean(
      Temperature,
      na.rm = TRUE
    ),
    Grain_Moisture = mean(
      Humidity,
      na.rm = TRUE
    ),
    .groups = "drop"
  )


# ------------------------------------------------------------
# 13.5 Total catch across the five species
# ------------------------------------------------------------

sampling_totals <- df %>%
  dplyr::group_by(
    Date_fixed,
    Time_Index,
    Silo,
    Zone,
    Trap_type
  ) %>%
  dplyr::summarise(
    Total_Count = sum(
      Count,
      na.rm = TRUE
    ),
    .groups = "drop"
  )


# ------------------------------------------------------------
# 13.6 Convert sampling categories to separate variables
# ------------------------------------------------------------

sampling_totals_wide <- sampling_totals %>%
  tidyr::pivot_wider(
    names_from = Trap_type,
    values_from = Total_Count,
    values_fill = 0
  ) %>%
  dplyr::rename(
    Trap_2m_Total = Trap_2m,
    Trap_top_Total = Trap_top,
    Trier_Total = Trier
  )


# ------------------------------------------------------------
# 13.7 Construct threshold-detection dataset
# ------------------------------------------------------------

fumigation_prediction_df <- sampling_totals_wide %>%
  dplyr::left_join(
    environmental_data,
    by = c(
      "Date_fixed",
      "Time_Index",
      "Silo",
      "Zone"
    )
  ) %>%
  dplyr::mutate(
    Zone = as.character(Zone)
  ) %>%
  dplyr::left_join(
    zone_sampling_mass,
    by = "Zone"
  ) %>%
  dplyr::mutate(
    Trier_Density_per_kg =
      Trier_Total / Trier_Sampled_kg,
    
    Threshold_exceeded =
      as.integer(
        Trier_Density_per_kg >=
          action_threshold_per_kg
      )
  ) %>%
  dplyr::select(
    Date_fixed,
    Time_Index,
    Silo,
    Zone,
    Trap_2m_Total,
    Trap_top_Total,
    Temperature,
    Grain_Moisture,
    Trier_Total,
    Trier_Samples,
    Trier_Sampled_kg,
    Trier_Density_per_kg,
    Threshold_exceeded
  ) %>%
  dplyr::arrange(
    Date_fixed,
    Silo,
    Zone
  )


# ------------------------------------------------------------
# 13.8 Descriptive threshold summaries
# ------------------------------------------------------------

threshold_prevalence <- fumigation_prediction_df %>%
  dplyr::count(
    Threshold_exceeded
  ) %>%
  dplyr::mutate(
    Percent = 100 * n / sum(n)
  )

threshold_by_zone <- fumigation_prediction_df %>%
  dplyr::group_by(
    Zone
  ) %>%
  dplyr::summarise(
    N = dplyr::n(),
    Threshold_Exceedances =
      sum(Threshold_exceeded),
    Percent_Exceeding =
      100 * mean(Threshold_exceeded),
    .groups = "drop"
  )

threshold_by_time <- fumigation_prediction_df %>%
  dplyr::group_by(
    Date_fixed,
    Time_Index
  ) %>%
  dplyr::summarise(
    N = dplyr::n(),
    Threshold_Exceedances =
      sum(Threshold_exceeded),
    Percent_Exceeding =
      100 * mean(Threshold_exceeded),
    .groups = "drop"
  )

cat("\n=== Threshold-detection dataset ===\n")
cat("Number of observations:", nrow(fumigation_prediction_df), "\n")

cat("\n=== Action-threshold prevalence ===\n")
print(
  threshold_prevalence,
  n = Inf,
  width = Inf
)

cat("\n=== Threshold exceedance by Zone ===\n")
print(
  threshold_by_zone,
  n = Inf,
  width = Inf
)

cat("\n=== Threshold exceedance over time ===\n")
print(
  threshold_by_time,
  n = Inf,
  width = Inf
)

write.csv(
  fumigation_prediction_df,
  "fumigation_detection_dataset.csv",
  row.names = FALSE
)


# ------------------------------------------------------------
# 13.9 Prepare modelling dataset
# ------------------------------------------------------------

detection_temp_mean <- mean(
  fumigation_prediction_df$Temperature,
  na.rm = TRUE
)

detection_temp_sd <- sd(
  fumigation_prediction_df$Temperature,
  na.rm = TRUE
)

detection_moist_mean <- mean(
  fumigation_prediction_df$Grain_Moisture,
  na.rm = TRUE
)

detection_moist_sd <- sd(
  fumigation_prediction_df$Grain_Moisture,
  na.rm = TRUE
)

detection_time_mean <- mean(
  fumigation_prediction_df$Time_Index,
  na.rm = TRUE
)

detection_time_sd <- sd(
  fumigation_prediction_df$Time_Index,
  na.rm = TRUE
)

detection_df <- fumigation_prediction_df %>%
  dplyr::mutate(
    Zone = factor(
      Zone,
      levels = c(
        "CENTER",
        "MIDDLE",
        "EDGE"
      )
    ),
    
    Silo = factor(Silo),
    
    Trap_2m_log =
      log1p(Trap_2m_Total),
    
    Trap_top_log =
      log1p(Trap_top_Total),
    
    Temp_z =
      (
        Temperature -
          detection_temp_mean
      ) /
      detection_temp_sd,
    
    Moist_z =
      (
        Grain_Moisture -
          detection_moist_mean
      ) /
      detection_moist_sd,
    
    Time_z =
      (
        Time_Index -
          detection_time_mean
      ) /
      detection_time_sd
  )


# ------------------------------------------------------------
# 13.10 Candidate logistic models
# ------------------------------------------------------------

m_detection_env_time <- glm(
  Threshold_exceeded ~
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo,
  data = detection_df,
  family = binomial(
    link = "logit"
  )
)

m_detection_2m_time <- glm(
  Threshold_exceeded ~
    Trap_2m_log +
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo,
  data = detection_df,
  family = binomial(
    link = "logit"
  )
)

m_detection_top_time <- glm(
  Threshold_exceeded ~
    Trap_top_log +
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo,
  data = detection_df,
  family = binomial(
    link = "logit"
  )
)

m_detection_both_time <- glm(
  Threshold_exceeded ~
    Trap_2m_log +
    Trap_top_log +
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo,
  data = detection_df,
  family = binomial(
    link = "logit"
  )
)


# ------------------------------------------------------------
# 13.11 Candidate-model comparison
# ------------------------------------------------------------

detection_model_comparison <- data.frame(
  Model = c(
    "Environment + nonlinear time",
    "Trap_2m + environment + nonlinear time",
    "Trap_top + environment + nonlinear time",
    "Both traps + environment + nonlinear time"
  ),
  AIC = c(
    AIC(m_detection_env_time),
    AIC(m_detection_2m_time),
    AIC(m_detection_top_time),
    AIC(m_detection_both_time)
  )
) %>%
  dplyr::arrange(
    AIC
  ) %>%
  dplyr::mutate(
    Delta_AIC =
      AIC - min(AIC)
  )

cat("\n=== Threshold-model AIC comparison ===\n")
print(
  detection_model_comparison,
  row.names = FALSE
)


# Incremental value of probe-trap predictors

lrt_env_vs_both <- anova(
  m_detection_env_time,
  m_detection_both_time,
  test = "Chisq"
)

lrt_top_vs_both <- anova(
  m_detection_top_time,
  m_detection_both_time,
  test = "Chisq"
)

lrt_2m_vs_both <- anova(
  m_detection_2m_time,
  m_detection_both_time,
  test = "Chisq"
)

cat("\n=== Environment + time vs both traps + environment + time ===\n")
print(lrt_env_vs_both)

cat("\n=== Trap_top model vs both-trap model ===\n")
print(lrt_top_vs_both)

cat("\n=== Trap_2m model vs both-trap model ===\n")
print(lrt_2m_vs_both)


# ------------------------------------------------------------
# 13.12 Leave-one-sampling-date-out cross-validation
# ------------------------------------------------------------

candidate_time_formulas <- list(
  
  "Environment + nonlinear time" =
    Threshold_exceeded ~
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo,
  
  "Trap_2m + environment + nonlinear time" =
    Threshold_exceeded ~
    Trap_2m_log +
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo,
  
  "Trap_top + environment + nonlinear time" =
    Threshold_exceeded ~
    Trap_top_log +
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo,
  
  "Both traps + environment + nonlinear time" =
    Threshold_exceeded ~
    Trap_2m_log +
    Trap_top_log +
    Temp_z * Moist_z +
    splines::ns(Time_z, df = 3) +
    Zone +
    Silo
)

sampling_dates <- sort(
  unique(
    detection_df$Date_fixed
  )
)

cv_time_predictions <- list()
cv_index <- 1

for (d in seq_along(sampling_dates)) {
  
  held_out_date <- sampling_dates[d]
  
  train_data <- detection_df %>%
    dplyr::filter(
      Date_fixed != held_out_date
    )
  
  test_data <- detection_df %>%
    dplyr::filter(
      Date_fixed == held_out_date
    )
  
  
  # Training-set standardization only
  
  training_temp_mean <- mean(
    train_data$Temperature,
    na.rm = TRUE
  )
  
  training_temp_sd <- sd(
    train_data$Temperature,
    na.rm = TRUE
  )
  
  training_moist_mean <- mean(
    train_data$Grain_Moisture,
    na.rm = TRUE
  )
  
  training_moist_sd <- sd(
    train_data$Grain_Moisture,
    na.rm = TRUE
  )
  
  training_time_mean <- mean(
    train_data$Time_Index,
    na.rm = TRUE
  )
  
  training_time_sd <- sd(
    train_data$Time_Index,
    na.rm = TRUE
  )
  
  
  train_data <- train_data %>%
    dplyr::mutate(
      Trap_2m_log =
        log1p(Trap_2m_Total),
      
      Trap_top_log =
        log1p(Trap_top_Total),
      
      Temp_z =
        (
          Temperature -
            training_temp_mean
        ) /
        training_temp_sd,
      
      Moist_z =
        (
          Grain_Moisture -
            training_moist_mean
        ) /
        training_moist_sd,
      
      Time_z =
        (
          Time_Index -
            training_time_mean
        ) /
        training_time_sd
    )
  
  test_data <- test_data %>%
    dplyr::mutate(
      Trap_2m_log =
        log1p(Trap_2m_Total),
      
      Trap_top_log =
        log1p(Trap_top_Total),
      
      Temp_z =
        (
          Temperature -
            training_temp_mean
        ) /
        training_temp_sd,
      
      Moist_z =
        (
          Grain_Moisture -
            training_moist_mean
        ) /
        training_moist_sd,
      
      Time_z =
        (
          Time_Index -
            training_time_mean
        ) /
        training_time_sd
    )
  
  
  train_data$Zone <- factor(
    train_data$Zone,
    levels = levels(detection_df$Zone)
  )
  
  test_data$Zone <- factor(
    test_data$Zone,
    levels = levels(detection_df$Zone)
  )
  
  train_data$Silo <- factor(
    train_data$Silo,
    levels = levels(detection_df$Silo)
  )
  
  test_data$Silo <- factor(
    test_data$Silo,
    levels = levels(detection_df$Silo)
  )
  
  
  for (model_name in names(candidate_time_formulas)) {
    
    cv_model <- glm(
      formula =
        candidate_time_formulas[[model_name]],
      data = train_data,
      family = binomial(
        link = "logit"
      )
    )
    
    cv_probability <- predict(
      cv_model,
      newdata = test_data,
      type = "response"
    )
    
    cv_time_predictions[[cv_index]] <- data.frame(
      Model = model_name,
      Date_fixed = test_data$Date_fixed,
      Observed =
        test_data$Threshold_exceeded,
      Predicted_Probability =
        as.numeric(cv_probability)
    )
    
    cv_index <- cv_index + 1
  }
}

cv_time_predictions <- dplyr::bind_rows(
  cv_time_predictions
)


# ------------------------------------------------------------
# 13.13 ROC AUC function
# ------------------------------------------------------------

auc_binary <- function(
    observed,
    predicted
) {
  
  valid <- complete.cases(
    observed,
    predicted
  )
  
  observed <- observed[valid]
  predicted <- predicted[valid]
  
  positive_scores <- predicted[
    observed == 1
  ]
  
  negative_scores <- predicted[
    observed == 0
  ]
  
  n_positive <- length(
    positive_scores
  )
  
  n_negative <- length(
    negative_scores
  )
  
  if (
    n_positive == 0 ||
    n_negative == 0
  ) {
    return(NA_real_)
  }
  
  combined_scores <- c(
    positive_scores,
    negative_scores
  )
  
  combined_ranks <- rank(
    combined_scores,
    ties.method = "average"
  )
  
  positive_rank_sum <- sum(
    combined_ranks[
      seq_len(n_positive)
    ]
  )
  
  (
    positive_rank_sum -
      n_positive *
      (n_positive + 1) / 2
  ) /
    (
      n_positive *
        n_negative
    )
}


# ------------------------------------------------------------
# 13.14 Cross-validated candidate-model performance
# ------------------------------------------------------------

cv_time_performance <- cv_time_predictions %>%
  dplyr::group_by(
    Model
  ) %>%
  dplyr::summarise(
    
    ROC_AUC =
      auc_binary(
        Observed,
        Predicted_Probability
      ),
    
    Brier_Score =
      mean(
        (
          Predicted_Probability -
            Observed
        )^2,
        na.rm = TRUE
      ),
    
    Sensitivity_0.5 =
      sum(
        Predicted_Probability >= 0.5 &
          Observed == 1,
        na.rm = TRUE
      ) /
      sum(
        Observed == 1,
        na.rm = TRUE
      ),
    
    Specificity_0.5 =
      sum(
        Predicted_Probability < 0.5 &
          Observed == 0,
        na.rm = TRUE
      ) /
      sum(
        Observed == 0,
        na.rm = TRUE
      ),
    
    .groups = "drop"
  ) %>%
  dplyr::arrange(
    dplyr::desc(ROC_AUC)
  )

cat("\n=== Leave-one-date-out performance ===\n")
print(
  as.data.frame(
    cv_time_performance
  ),
  row.names = FALSE
)


# ------------------------------------------------------------
# 13.15 Final threshold model
# ------------------------------------------------------------

# Final model:
# Environment + nonlinear time
#
# Probe-trap counts are not included in the final model.

m_detection_final <- m_detection_env_time

cat("\n=== Final threshold model ===\n")
print(
  summary(
    m_detection_final
  )
)

final_time_cv <- cv_time_predictions %>%
  dplyr::filter(
    Model ==
      "Environment + nonlinear time"
  )


# ------------------------------------------------------------
# 13.16 Probability-threshold performance
# ------------------------------------------------------------

probability_thresholds <- seq(
  0.01,
  0.99,
  by = 0.01
)

threshold_results <- vector(
  mode = "list",
  length = length(
    probability_thresholds
  )
)

for (i in seq_along(probability_thresholds)) {
  
  cutoff <- probability_thresholds[i]
  
  predicted_class <- as.integer(
    final_time_cv$Predicted_Probability >= cutoff
  )
  
  observed_class <- final_time_cv$Observed
  
  TP <- sum(
    predicted_class == 1 &
      observed_class == 1,
    na.rm = TRUE
  )
  
  TN <- sum(
    predicted_class == 0 &
      observed_class == 0,
    na.rm = TRUE
  )
  
  FP <- sum(
    predicted_class == 1 &
      observed_class == 0,
    na.rm = TRUE
  )
  
  FN <- sum(
    predicted_class == 0 &
      observed_class == 1,
    na.rm = TRUE
  )
  
  
  Sensitivity <- if (
    TP + FN > 0
  ) {
    TP / (TP + FN)
  } else {
    NA_real_
  }
  
  Specificity <- if (
    TN + FP > 0
  ) {
    TN / (TN + FP)
  } else {
    NA_real_
  }
  
  PPV <- if (
    TP + FP > 0
  ) {
    TP / (TP + FP)
  } else {
    NA_real_
  }
  
  NPV <- if (
    TN + FN > 0
  ) {
    TN / (TN + FN)
  } else {
    NA_real_
  }
  
  threshold_results[[i]] <- data.frame(
    Probability_Threshold = cutoff,
    Sensitivity = Sensitivity,
    Specificity = Specificity,
    PPV = PPV,
    NPV = NPV,
    Youden_J =
      Sensitivity +
      Specificity -
      1
  )
}

final_threshold_performance <- dplyr::bind_rows(
  threshold_results
)


# ------------------------------------------------------------
# 13.17 Balanced cutoff: maximum Youden J
# ------------------------------------------------------------

final_best_youden <- final_threshold_performance %>%
  dplyr::filter(
    !is.na(Youden_J)
  ) %>%
  dplyr::arrange(
    dplyr::desc(Youden_J),
    dplyr::desc(Sensitivity),
    dplyr::desc(Specificity)
  ) %>%
  dplyr::slice(1)

cat("\n=== Final model: best Youden cutoff ===\n")

print(
  as.data.frame(final_best_youden),
  row.names = FALSE
)


# ------------------------------------------------------------
# 13.18 High-sensitivity cutoff
# ------------------------------------------------------------

final_high_sensitivity <- final_threshold_performance %>%
  dplyr::filter(
    Sensitivity >= 0.90
  ) %>%
  dplyr::arrange(
    dplyr::desc(Specificity),
    dplyr::desc(PPV),
    dplyr::desc(Probability_Threshold)
  ) %>%
  dplyr::slice(1)

cat("\n=== Final model: >= 90% sensitivity cutoff ===\n")

print(
  as.data.frame(final_high_sensitivity),
  row.names = FALSE
)


# ------------------------------------------------------------
# 13.19 Cross-validated calibration
# ------------------------------------------------------------

final_calibration_data <- final_time_cv %>%
  dplyr::filter(
    !is.na(Observed),
    !is.na(Predicted_Probability)
  ) %>%
  dplyr::mutate(
    Probability_Clamped = pmin(
      pmax(
        Predicted_Probability,
        1e-6
      ),
      1 - 1e-6
    ),
    
    Prediction_Logit =
      qlogis(
        Probability_Clamped
      )
  )

final_calibration_slope_model <- glm(
  Observed ~ Prediction_Logit,
  data = final_calibration_data,
  family = binomial(
    link = "logit"
  )
)

final_calibration_intercept_model <- glm(
  Observed ~
    1 +
    offset(Prediction_Logit),
  data = final_calibration_data,
  family = binomial(
    link = "logit"
  )
)

final_calibration_summary <- data.frame(
  
  Calibration_Intercept = unname(
    coef(final_calibration_intercept_model)["(Intercept)"]
  ),
  
  Calibration_Intercept_SE = unname(
    summary(final_calibration_intercept_model)$coefficients[
      "(Intercept)", "Std. Error"
    ]
  ),
  
  Calibration_Slope = unname(
    coef(final_calibration_slope_model)["Prediction_Logit"]
  ),
  
  Calibration_Slope_SE = unname(
    summary(final_calibration_slope_model)$coefficients[
      "Prediction_Logit", "Std. Error"
    ]
  )
)

cat("\n=== Final model: cross-validated calibration ===\n")

print(
  final_calibration_summary,
  row.names = FALSE
)


# ------------------------------------------------------------
# 13.20 Save threshold-analysis results
# ------------------------------------------------------------

write.csv(
  detection_model_comparison,
  "time_adjusted_detection_model_AIC.csv",
  row.names = FALSE
)

write.csv(
  cv_time_predictions,
  "time_adjusted_detection_crossvalidated_predictions.csv",
  row.names = FALSE
)

write.csv(
  cv_time_performance,
  "time_adjusted_detection_crossvalidated_performance.csv",
  row.names = FALSE
)

write.csv(
  final_threshold_performance,
  "final_time_detection_threshold_performance.csv",
  row.names = FALSE
)

write.csv(
  final_best_youden,
  "final_time_detection_best_youden.csv",
  row.names = FALSE
)

write.csv(
  final_high_sensitivity,
  "final_time_detection_high_sensitivity.csv",
  row.names = FALSE
)

write.csv(
  final_calibration_summary,
  "final_time_detection_calibration.csv",
  row.names = FALSE
)
# ============================================================
# 14. TRIER SPECIES-DENSITY MODELS
# ============================================================

# Grain-trier observations are modelled as counts with an
# offset for the sampled wheat mass. Model predictions can
# therefore be expressed directly as expected insects/kg.
#
# Repeated observations from each Species x Silo x Zone
# combination are represented by TrierSeriesID.


# ------------------------------------------------------------
# 14.1 Construct Trier-only species-density dataset
# ------------------------------------------------------------

trier_species_df <- df %>%
  dplyr::filter(
    Trap_type == "Trier"
  ) %>%
  dplyr::mutate(
    
    Species = factor(
      Species
    ),
    
    Silo = factor(
      Silo
    ),
    
    Zone = factor(
      Zone,
      levels = c(
        "CENTER",
        "MIDDLE",
        "EDGE"
      )
    ),
    
    Grain_Moisture = Humidity,
    
    Sampled_kg = dplyr::case_when(
      Zone == "CENTER" ~ 1.50,
      Zone == "MIDDLE" ~ 3.75,
      Zone == "EDGE"   ~ 5.25,
      TRUE ~ NA_real_
    ),
    
    Density_per_kg =
      Count / Sampled_kg,
    
    TrierSeriesID = interaction(
      Species,
      Silo,
      Zone,
      drop = TRUE
    )
  )


cat("\n=== Trier species-density dataset ===\n")

cat(
  "Number of observations:",
  nrow(trier_species_df),
  "\n"
)

cat(
  "Number of repeated Trier series:",
  nlevels(trier_species_df$TrierSeriesID),
  "\n"
)

cat("\nObservations by species:\n")
print(
  table(
    trier_species_df$Species
  )
)

cat("\nObservations by zone:\n")
print(
  table(
    trier_species_df$Zone
  )
)

cat("\nSampled wheat mass by zone:\n")
print(
  unique(
    trier_species_df[
      c(
        "Zone",
        "Sampled_kg"
      )
    ]
  ),
  row.names = FALSE
)


# ------------------------------------------------------------
# 14.2 Standardize environmental and temporal predictors
# ------------------------------------------------------------

trier_temp_mean <- mean(
  trier_species_df$Temperature,
  na.rm = TRUE
)

trier_temp_sd <- sd(
  trier_species_df$Temperature,
  na.rm = TRUE
)

trier_moist_mean <- mean(
  trier_species_df$Grain_Moisture,
  na.rm = TRUE
)

trier_moist_sd <- sd(
  trier_species_df$Grain_Moisture,
  na.rm = TRUE
)

trier_time_mean <- mean(
  trier_species_df$Time_Index,
  na.rm = TRUE
)

trier_time_sd <- sd(
  trier_species_df$Time_Index,
  na.rm = TRUE
)


trier_species_df <- trier_species_df %>%
  dplyr::mutate(
    
    Temp_z =
      (
        Temperature -
          trier_temp_mean
      ) /
      trier_temp_sd,
    
    Moist_z =
      (
        Grain_Moisture -
          trier_moist_mean
      ) /
      trier_moist_sd,
    
    Time_z =
      (
        Time_Index -
          trier_time_mean
      ) /
      trier_time_sd
  )


# ------------------------------------------------------------
# 14.3 Common environmental-response NB model
# ------------------------------------------------------------

# Species-specific nonlinear temporal trajectories are allowed,
# whereas Temperature x Grain Moisture is common across species.

m_trier_common_env <- glmmTMB(
  Count ~
    Species *
    splines::ns(
      Time_z,
      df = 3
    ) +
    Temp_z *
    Moist_z +
    offset(
      log(
        Sampled_kg
      )
    ) +
    (
      1 |
        TrierSeriesID
    ),
  data = trier_species_df,
  family = nbinom2(
    link = "log"
  )
)


# ------------------------------------------------------------
# 14.4 Species-specific environmental-response NB model
# ------------------------------------------------------------

m_trier_species_env <- glmmTMB(
  Count ~
    Species *
    splines::ns(
      Time_z,
      df = 3
    ) +
    Species *
    Temp_z *
    Moist_z +
    offset(
      log(
        Sampled_kg
      )
    ) +
    (
      1 |
        TrierSeriesID
    ),
  data = trier_species_df,
  family = nbinom2(
    link = "log"
  )
)


# ------------------------------------------------------------
# 14.5 Species-specific environmental-response ZINB model
# ------------------------------------------------------------

m_trier_species_env_zinb <- glmmTMB(
  Count ~
    Species *
    splines::ns(
      Time_z,
      df = 3
    ) +
    Species *
    Temp_z *
    Moist_z +
    offset(
      log(
        Sampled_kg
      )
    ) +
    (
      1 |
        TrierSeriesID
    ),
  ziformula =
    ~ Species,
  data = trier_species_df,
  family = nbinom2(
    link = "log"
  )
)


# ------------------------------------------------------------
# 14.6 Main model comparison
# ------------------------------------------------------------

trier_model_comparison <- data.frame(
  
  Model = c(
    "Common environmental response NB",
    "Species-specific environmental response NB",
    "Species-specific environmental response ZINB"
  ),
  
  AIC = c(
    AIC(
      m_trier_common_env
    ),
    AIC(
      m_trier_species_env
    ),
    AIC(
      m_trier_species_env_zinb
    )
  )
) %>%
  dplyr::arrange(
    AIC
  ) %>%
  dplyr::mutate(
    Delta_AIC =
      AIC -
      min(AIC)
  )


cat("\n=== Trier density model AIC comparison ===\n")

print(
  trier_model_comparison,
  row.names = FALSE
)


# ------------------------------------------------------------
# 14.7 Test species-specific environmental responses
# ------------------------------------------------------------

species_environment_lrt <- anova(
  m_trier_common_env,
  m_trier_species_env,
  test = "Chisq"
)

cat(
  "\n=== Common vs species-specific environmental response ===\n"
)

print(
  species_environment_lrt
)


# ------------------------------------------------------------
# 14.8 Environmental interaction comparison
# ------------------------------------------------------------

m_trier_additive_env <- glmmTMB(
  Count ~
    Species *
    splines::ns(
      Time_z,
      df = 3
    ) +
    Temp_z +
    Moist_z +
    offset(
      log(
        Sampled_kg
      )
    ) +
    (
      1 |
        TrierSeriesID
    ),
  data = trier_species_df,
  family = nbinom2(
    link = "log"
  )
)


environment_interaction_comparison <- data.frame(
  
  Model = c(
    "Additive temperature + moisture",
    "Temperature x moisture interaction"
  ),
  
  AIC = c(
    AIC(
      m_trier_additive_env
    ),
    AIC(
      m_trier_common_env
    )
  )
) %>%
  dplyr::arrange(
    AIC
  ) %>%
  dplyr::mutate(
    Delta_AIC =
      AIC -
      min(AIC)
  )


environment_interaction_lrt <- anova(
  m_trier_additive_env,
  m_trier_common_env,
  test = "Chisq"
)


cat(
  "\n=== Environmental interaction AIC comparison ===\n"
)

print(
  environment_interaction_comparison,
  row.names = FALSE
)

cat(
  "\n=== Additive vs Temperature x Grain Moisture interaction ===\n"
)

print(
  environment_interaction_lrt
)


# ------------------------------------------------------------
# 14.9 Model summaries
# ------------------------------------------------------------

cat(
  "\n=== Common environmental-response NB model ===\n"
)

print(
  summary(
    m_trier_common_env
  )
)


cat(
  "\n=== Species-specific environmental-response NB model ===\n"
)

print(
  summary(
    m_trier_species_env
  )
)


cat(
  "\n=== Species-specific environmental-response ZINB model ===\n"
)

print(
  summary(
    m_trier_species_env_zinb
  )
)


# ------------------------------------------------------------
# 14.10 DHARMa diagnostics for primary Trier-density model
# ------------------------------------------------------------

set.seed(42)

sim_trier <- DHARMa::simulateResiduals(
  fittedModel = m_trier_common_env,
  n = 1000,
  plot = FALSE
)


trier_uniformity <- DHARMa::testUniformity(
  sim_trier
)

trier_dispersion <- DHARMa::testDispersion(
  sim_trier
)

trier_zeros <- DHARMa::testZeroInflation(
  sim_trier
)

set.seed(42)

trier_outliers <- DHARMa::testOutliers(
  sim_trier,
  type = "bootstrap",
  nBoot = 1000
)


cat("\n=== Trier-model DHARMa diagnostics ===\n")

print(
  trier_uniformity
)

print(
  trier_dispersion
)

print(
  trier_zeros
)

print(
  trier_outliers
)


png(
  "Trier_density_DHARMa_diagnostics.png",
  width = 1600,
  height = 1200
)

plot(
  sim_trier
)

dev.off()


trier_diagnostic_summary <- data.frame(
  Uniformity_p =
    trier_uniformity$p.value,
  Dispersion_p =
    trier_dispersion$p.value,
  Zero_inflation_p =
    trier_zeros$p.value,
  Bootstrap_outlier_p =
    trier_outliers$p.value
)

print(
  trier_diagnostic_summary,
  row.names = FALSE
)


# ------------------------------------------------------------
# 14.11 Primary Trier-density model
# ------------------------------------------------------------

m_trier_final <- m_trier_common_env


# ------------------------------------------------------------
# 14.12 Save Trier-density results
# ------------------------------------------------------------

write.csv(
  trier_species_df,
  "trier_species_density_dataset.csv",
  row.names = FALSE
)

write.csv(
  trier_model_comparison,
  "trier_density_model_comparison.csv",
  row.names = FALSE
)

write.csv(
  environment_interaction_comparison,
  "trier_environment_interaction_comparison.csv",
  row.names = FALSE
)

write.csv(
  trier_diagnostic_summary,
  "trier_density_diagnostic_summary.csv",
  row.names = FALSE
)
# ============================================================
# 15. ENVIRONMENTAL INFESTATION NOMOGRAMS
# ============================================================

# Nomograms are based on the primary Trier-density model.
#
# Predictions:
# - are restricted to the observed joint Temperature x
#   Grain Moisture domain;
# - exclude random effects (population-level predictions);
# - use Sampled_kg = 1, so predictions are insects/kg;
# - are evaluated at all 15 observed sampling occasions and
#   averaged across time.
#
# The literature-based management reference of 2 insects/kg
# is displayed only for the overall predicted infestation density.


# ------------------------------------------------------------
# 15.1 Observed joint environmental support
# ------------------------------------------------------------

trier_environment_support <- trier_species_df %>%
  dplyr::select(
    Temperature,
    Grain_Moisture
  ) %>%
  dplyr::distinct()


temperature_sequence <- seq(
  min(
    trier_environment_support$Temperature,
    na.rm = TRUE
  ),
  max(
    trier_environment_support$Temperature,
    na.rm = TRUE
  ),
  length.out = 120
)

moisture_sequence <- seq(
  min(
    trier_environment_support$Grain_Moisture,
    na.rm = TRUE
  ),
  max(
    trier_environment_support$Grain_Moisture,
    na.rm = TRUE
  ),
  length.out = 120
)


nomogram_environment_grid <- expand.grid(
  Temperature = temperature_sequence,
  Grain_Moisture = moisture_sequence
)


# ------------------------------------------------------------
# 15.2 Restrict prediction grid to observed joint support
# ------------------------------------------------------------

hull_index <- chull(
  trier_environment_support$Temperature,
  trier_environment_support$Grain_Moisture
)

environment_hull <- trier_environment_support[
  hull_index,
  ,
  drop = FALSE
]

environment_hull <- rbind(
  environment_hull,
  environment_hull[1, ]
)


point_in_polygon <- function(
    x,
    y,
    polygon_x,
    polygon_y
) {
  
  n_polygon <- length(
    polygon_x
  )
  
  inside <- rep(
    FALSE,
    length(x)
  )
  
  j <- n_polygon
  
  for (i in seq_len(n_polygon)) {
    
    intersects <- (
      (
        polygon_y[i] > y
      ) !=
        (
          polygon_y[j] > y
        )
    ) & (
      x <
        (
          polygon_x[j] -
            polygon_x[i]
        ) *
        (
          y -
            polygon_y[i]
        ) /
        (
          polygon_y[j] -
            polygon_y[i] +
            1e-12
        ) +
        polygon_x[i]
    )
    
    inside <- xor(
      inside,
      intersects
    )
    
    j <- i
  }
  
  inside
}


nomogram_environment_grid$Inside_Support <-
  point_in_polygon(
    
    x =
      nomogram_environment_grid$Temperature,
    
    y =
      nomogram_environment_grid$Grain_Moisture,
    
    polygon_x =
      environment_hull$Temperature,
    
    polygon_y =
      environment_hull$Grain_Moisture
  )


nomogram_environment_grid <-
  nomogram_environment_grid %>%
  dplyr::filter(
    Inside_Support
  )


# ------------------------------------------------------------
# 15.3 Standardize environmental predictors
# ------------------------------------------------------------

nomogram_environment_grid <-
  nomogram_environment_grid %>%
  dplyr::mutate(
    
    Temp_z =
      (
        Temperature -
          trier_temp_mean
      ) /
      trier_temp_sd,
    
    Moist_z =
      (
        Grain_Moisture -
          trier_moist_mean
      ) /
      trier_moist_sd
  )


# ------------------------------------------------------------
# 15.4 Observed sampling occasions
# ------------------------------------------------------------

standardization_times <- trier_species_df %>%
  dplyr::distinct(
    Time_Index,
    Time_z
  ) %>%
  dplyr::arrange(
    Time_Index
  )


cat(
  "\nNumber of sampling occasions used for time standardization:\n"
)

print(
  nrow(
    standardization_times
  )
)


# ------------------------------------------------------------
# 15.5 Species-specific time-standardized predictions
# ------------------------------------------------------------

species_levels <- levels(
  trier_species_df$Species
)

reference_series_level <- levels(
  trier_species_df$TrierSeriesID
)[1]


prediction_results <- vector(
  mode = "list",
  length = length(
    species_levels
  )
)


for (species_index in seq_along(species_levels)) {
  
  species_name <-
    species_levels[species_index]
  
  cat(
    "\nPredicting species:",
    species_name,
    "\n"
  )
  
  
  # Cross each supported environmental combination
  # with all observed sampling occasions.
  
  prediction_data <- merge(
    
    nomogram_environment_grid %>%
      dplyr::select(
        Temperature,
        Grain_Moisture,
        Temp_z,
        Moist_z
      ),
    
    standardization_times %>%
      dplyr::select(
        Time_Index,
        Time_z
      ),
    
    by = NULL
  )
  
  
  prediction_data$Species <- factor(
    species_name,
    levels = species_levels
  )
  
  
  # Sampled_kg = 1 gives expected insects/kg directly.
  
  prediction_data$Sampled_kg <- 1
  
  
  # Valid placeholder for the random-effect grouping variable.
  # Random effects are excluded in prediction.
  
  prediction_data$TrierSeriesID <- factor(
    reference_series_level,
    levels = levels(
      trier_species_df$TrierSeriesID
    )
  )
  
  
  prediction_data$Predicted_Density_per_kg <-
    as.numeric(
      predict(
        m_trier_final,
        newdata = prediction_data,
        type = "response",
        re.form = NA
      )
    )
  
  
  # Average predicted density across all observed
  # sampling occasions.
  
  prediction_results[[species_index]] <-
    prediction_data %>%
    dplyr::group_by(
      Temperature,
      Grain_Moisture
    ) %>%
    dplyr::summarise(
      
      Expected_Density_per_kg =
        mean(
          Predicted_Density_per_kg,
          na.rm = TRUE
        ),
      
      .groups = "drop"
    ) %>%
    dplyr::mutate(
      Species = species_name
    )
}


species_nomogram_predictions <-
  dplyr::bind_rows(
    prediction_results
  )


cat(
  "\n=== Species-specific nomogram predictions completed ===\n"
)


# ------------------------------------------------------------
# 15.6 Overall predicted infestation density
# ------------------------------------------------------------

overall_nomogram_predictions <-
  species_nomogram_predictions %>%
  dplyr::group_by(
    Temperature,
    Grain_Moisture
  ) %>%
  dplyr::summarise(
    
    Expected_Total_Density_per_kg =
      sum(
        Expected_Density_per_kg
      ),
    
    .groups = "drop"
  )


cat(
  "\n=== Overall infestation predictions completed ===\n"
)


# ------------------------------------------------------------
# 15.7 Save numerical prediction surfaces
# ------------------------------------------------------------

write.csv(
  species_nomogram_predictions,
  "species_nomogram_predictions.csv",
  row.names = FALSE
)

write.csv(
  overall_nomogram_predictions,
  "overall_nomogram_predictions.csv",
  row.names = FALSE
)


# ============================================================
# 15.8 SPECIES-SPECIFIC NOMOGRAMS
# ============================================================

dir.create(
  "species_nomograms",
  showWarnings = FALSE
)


species_nomogram_plots <- list()


for (species_name in species_levels) {
  
  species_plot_data <-
    species_nomogram_predictions %>%
    dplyr::filter(
      Species == species_name
    )
  
  
  p_species <- ggplot(
    species_plot_data,
    aes(
      x = Temperature,
      y = Grain_Moisture
    )
  ) +
    
    geom_raster(
      aes(
        fill =
          Expected_Density_per_kg
      ),
      interpolate = TRUE
    ) +
    
    geom_point(
      data =
        trier_environment_support,
      aes(
        x = Temperature,
        y = Grain_Moisture
      ),
      inherit.aes = FALSE,
      size = 0.7,
      alpha = 0.25
    ) +
    
    scale_fill_viridis_c(
      name =
        "Expected\ninsects/kg"
    ) +
    
    labs(
      title = species_name,
      subtitle =
        "Population-level, time-standardized predicted infestation density",
      x =
        "Grain temperature (°C)",
      y =
        "Grain moisture content (%)"
    ) +
    
    theme_bw(
      base_size = 11
    ) +
    
    theme(
      panel.grid =
        element_blank(),
      
      plot.title =
        element_text(
          face = "italic",
          size = 13
        ),
      
      plot.subtitle =
        element_text(
          size = 9
        )
    )
  
  
  species_nomogram_plots[[species_name]] <-
    p_species
  
  
  safe_species_name <- gsub(
    "[^A-Za-z0-9]+",
    "_",
    species_name
  )
  
  
  ggsave(
    filename = paste0(
      "species_nomograms/",
      safe_species_name,
      "_nomogram.png"
    ),
    plot = p_species,
    width = 7,
    height = 5.5,
    dpi = 300
  )
}


# ============================================================
# 15.9 OVERALL MANAGEMENT-REFERENCE NOMOGRAM
# ============================================================

fumigation_density_threshold <-
  action_threshold_per_kg


p_overall_nomogram <- ggplot(
  overall_nomogram_predictions,
  aes(
    x = Temperature,
    y = Grain_Moisture
  )
) +
  
  geom_raster(
    aes(
      fill =
        Expected_Total_Density_per_kg
    ),
    interpolate = TRUE
  ) +
  
  geom_contour(
    aes(
      z =
        Expected_Total_Density_per_kg
    ),
    breaks =
      fumigation_density_threshold,
    linewidth = 1
  ) +
  
  geom_point(
    data =
      trier_environment_support,
    aes(
      x = Temperature,
      y = Grain_Moisture
    ),
    inherit.aes = FALSE,
    size = 0.7,
    alpha = 0.25
  ) +
  
  scale_fill_viridis_c(
    name =
      "Expected total\ninsects/kg"
  ) +
  
  labs(
    title =
      "Environmental nomogram for the 2 insects/kg management reference",
    
    subtitle =
      "Population-level, time-standardized predicted total infestation density",
    
    x =
      "Grain temperature (°C)",
    
    y =
      "Grain moisture content (%)",
    
    caption =
      paste0(
        "Contour denotes the literature-based management reference of ",
        fumigation_density_threshold,
        " insects/kg."
      )
  ) +
  
  theme_bw(
    base_size = 11
  ) +
  
  theme(
    panel.grid =
      element_blank(),
    
    plot.title =
      element_text(
        face = "bold",
        size = 13
      ),
    
    plot.subtitle =
      element_text(
        size = 9
      )
  )


ggsave(
  filename =
    "management_reference_nomogram.png",
  plot =
    p_overall_nomogram,
  width = 7.5,
  height = 6,
  dpi = 300
)


# ============================================================
# 15.10 FINAL JOURNAL-STYLE SPECIES NOMOGRAM FIGURE
# ============================================================

# Common plotting ranges
common_fill_limits <- range(
  species_nomogram_predictions$Expected_Density_per_kg,
  na.rm = TRUE
)

common_x_limits <- range(
  trier_environment_support$Temperature,
  na.rm = TRUE
)

common_y_limits <- range(
  trier_environment_support$Grain_Moisture,
  na.rm = TRUE
)


# Function for a single species panel
make_species_panel <- function(species_name, species_label) {
  
  plot_data <- species_nomogram_predictions %>%
    dplyr::filter(Species == species_name)
  
  ggplot(
    plot_data,
    aes(
      x = Temperature,
      y = Grain_Moisture,
      fill = Expected_Density_per_kg
    )
  ) +
    geom_raster(interpolate = TRUE) +
    geom_point(
      data = trier_environment_support,
      aes(x = Temperature, y = Grain_Moisture),
      inherit.aes = FALSE,
      size = 0.65,
      alpha = 0.22,
      shape = 16
    ) +
    scale_x_continuous(
      breaks = c(10, 20, 30, 40),
      expand = c(0, 0)
    ) +
    scale_y_continuous(
      breaks = c(9, 10, 11, 12, 13),
      expand = c(0, 0)
    ) +
    scale_fill_viridis_c(
      limits = common_fill_limits,
      name = "Expected\ninsects/kg",
      guide = guide_colorbar(
        title.position = "top",
        title.hjust = 0,
        barheight = grid::unit(42, "mm"),
        barwidth = grid::unit(6, "mm"),
        ticks = TRUE,
        frame.colour = NA
      )
    ) +
    labs(
      title = species_label,
      x = "Grain temperature (°C)",
      y = "Grain moisture content (%)"
    ) +
    coord_cartesian(
      xlim = common_x_limits,
      ylim = common_y_limits,
      expand = FALSE,
      clip = "on"
    ) +
    theme_classic(base_size = 10.5) +
    theme(
      panel.border = element_rect(
        colour = "black",
        fill = NA,
        linewidth = 0.45
      ),
      axis.line = element_blank(),
      axis.ticks = element_line(linewidth = 0.4),
      axis.ticks.length = grid::unit(2.2, "mm"),
      axis.text = element_text(size = 9, colour = "black"),
      axis.title = element_text(size = 10.5, colour = "black"),
      plot.title = element_text(
        face = "italic",
        size = 11.5,
        hjust = 0.5,
        margin = margin(b = 6)
      ),
      legend.title = element_text(
        size = 9.5,
        lineheight = 0.95
      ),
      legend.text = element_text(size = 8.5),
      plot.margin = margin(t = 5, r = 6, b = 5, l = 6)
    )
}


# Create five species panels
p1 <- make_species_panel(
  species_name = "Cryptolestes ferrugineus",
  species_label = "C. ferrugineus"
)

p2 <- make_species_panel(
  species_name = "Oryzaephilus surinamensis",
  species_label = "O. surinamensis"
)

p3 <- make_species_panel(
  species_name = "Rhyzopertha dominica",
  species_label = "R. dominica"
)

p4 <- make_species_panel(
  species_name = "Sitophilus oryzae",
  species_label = "S. oryzae"
)

p5 <- make_species_panel(
  species_name = "Tribolium castaneum",
  species_label = "T. castaneum"
)


# Symmetrical 3 + 2 layout
species_layout <- "
AABBCC
#DDEE#
"


# Assemble final figure
final_species_nomogram_figure <- wrap_plots(
  A = p1,
  B = p2,
  C = p3,
  D = p4,
  E = p5,
  design = species_layout,
  guides = "collect"
) +
  plot_annotation(
    title = "Species-specific infestation nomograms",
    subtitle = paste0(
      "Population-level, time-standardized predicted ",
      "infestation density across observed grain conditions"
    ),
    tag_levels = "A",
    theme = theme(
      plot.title = element_text(
        face = "bold",
        size = 16,
        hjust = 0,
        margin = margin(b = 4)
      ),
      plot.subtitle = element_text(
        size = 10.5,
        hjust = 0,
        margin = margin(b = 12)
      ),
      plot.tag = element_text(
        face = "bold",
        size = 10
      )
    )
  ) &
  theme(
    legend.position = "right",
    plot.tag.position = c(0.02, 0.98)
  )


# Collect duplicated axes and axis titles
final_species_nomogram_figure <- final_species_nomogram_figure +
  plot_layout(
    design = species_layout,
    guides = "collect",
    axes = "collect",
    axis_titles = "collect"
  )


# Display
print(final_species_nomogram_figure)


# Save outputs
ggsave(
  filename = "Figure_species_specific_nomograms_FINAL.png",
  plot = final_species_nomogram_figure,
  width = 12.5,
  height = 7.8,
  units = "in",
  dpi = 600,
  bg = "white"
)

ggsave(
  filename = "Figure_species_specific_nomograms_FINAL.tiff",
  plot = final_species_nomogram_figure,
  width = 12.5,
  height = 7.8,
  units = "in",
  dpi = 600,
  compression = "lzw",
  bg = "white"
)

ggsave(
  filename = "Figure_species_specific_nomograms_FINAL.pdf",
  plot = final_species_nomogram_figure,
  width = 12.5,
  height = 7.8,
  units = "in",
  bg = "white"
)

cat("\n=== FINAL JOURNAL FIGURE CREATED ===\n")
cat("Saved: Figure_species_specific_nomograms_FINAL.png\n")
# ============================================================
# COMPUTATIONAL ENVIRONMENT
# ============================================================

capture.output(
  sessionInfo(),
  file = "sessionInfo.txt"
)

if (requireNamespace("cmdstanr", quietly = TRUE)) {
  capture.output(
    tryCatch(
      cmdstanr::cmdstan_version(),
      error = function(e) conditionMessage(e)
    ),
    file = "cmdstan_version.txt"
  )
}