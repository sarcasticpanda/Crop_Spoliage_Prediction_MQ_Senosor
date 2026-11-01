# -*- coding: utf-8 -*-
"""
iot_processing.py
Reconstruction complete des Tableaux S1-S4 et des Figures 2 et S1 de l'article
"Conservation de la pomme de terre - comparaison de trois modes de stockage"
a partir des classeurs IoT bruts (campagnes 2024 et 2025).

Entree  : dossier contenant les fichiers chambre_*.xlsx / noeud_*.xlsx
Sortie  : Supplementary_Data_IoT.xlsx, Figure_IoT_main.png/.pdf, Figure_S1_IoT.png/.pdf

Dependances : pandas, numpy, openpyxl, matplotlib, scipy (optionnel)
Usage       : python3 iot_processing.py --input ./donnees_iot --output ./sortie
"""
import argparse, os, glob
import numpy as np, pandas as pd
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

# ---------------------------------------------------------------- configuration
SPEC = {
 ('Frigo', 2024): ["chambre_2_frigo_7degC_donnees_organisees_2024.xlsx"],
 ('Frigo', 2025): ["chambre_7DEG_donnees_organisees_2025.xlsx"],
 ('Hu',    2024): [f"chambre_humidificateur_noeud_{i}_donnees_organisees_2024.xlsx" for i in range(1, 6)],
 ('Hu',    2025): [f"chambre_humidificateur_noeud_{i}_donnees_organisees_2025.xlsx" for i in range(1, 6)],
 ('Serre', 2024): ["chambre_humidificateur_noeud_serre_donnees_organisees_2024.xlsx"],
 ('Serre', 2025): ["noeud_serre_donnees_organisees_2025.xlsx"],
 ('Ext',   2024): ["chambre_humidificateur_noeud_exterieur_donnees_organisees_2024.xlsx"],
 ('Ext',   2025): ["chambre_humidificateur_noeud_externe_1_donnees_organisees_2025.xlsx",
                   "chambre_humidificateur_noeud_externe_2_donnees_organisees_2025.xlsx"],
}
LAB = {'Frigo': '7 °C', 'Hu': 'H', 'Serre': 'Trad', 'Ext': 'Outdoor'}
COL = {'Frigo': '#1f5f8b', 'Hu': '#2e8b57', 'Serre': '#c0392b', 'Ext': '#7f8c8d'}
ORDER = ['Frigo', 'Hu', 'Serre']
POR = ['P1 (00-06h)', 'P2 (06-12h)', 'P3 (12-18h)', 'P4 (18-24h)']
PSH = ['P1\n00–06 h', 'P2\n06–12 h', 'P3\n12–18 h', 'P4\n18–24 h']

# Pertes finales publiees (Tableau 5 de l'article) et durees de conservation
LOSSES = {2024: {'Frigo': (3.25, 88), 'Hu': (5.58, 88), 'Serre': (7.11, 88)},
          2025: {'Frigo': (2.73, 72), 'Hu': (4.89, 72), 'Serre': (7.16, 72)}}

# ------------------------------------------------------------------ chargement
def _read(path, sheet, frag):
    try:
        df = pd.read_excel(path, sheet_name=sheet)
    except Exception:
        return None
    cols = [c for c in df.columns if frag.lower() in c.lower()]
    if not cols or 'Date' not in df.columns or 'Heure' not in df.columns:
        return None
    df = df[['Date', 'Heure', cols[0]]].copy()
    df.columns = ['Date', 'Heure', 'val']
    df['val'] = pd.to_numeric(df['val'], errors='coerce')
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df = df.dropna(subset=['Date'])
    ts = pd.to_datetime(df['Date'].dt.strftime('%Y-%m-%d') + ' '
                        + df['Heure'].astype(str).str.slice(0, 8), errors='coerce')
    df['ts'] = ts
    return df.dropna(subset=['ts'])[['ts', 'val']]


def load(indir):
    """Assemble tous les noeuds en une table longue (ts, T, HR, Tc, CO2, mode, year, node)."""
    frames = []
    for (mode, year), files in SPEC.items():
        for f in files:
            p = os.path.join(indir, f)
            if not os.path.exists(p):
                print(f"  [manquant] {f}")
                continue
            t = _read(p, 'Temperature_brut', 'Temperature')
            h = _read(p, 'Humidite_brut', 'Humidite')
            if t is None or h is None:
                continue
            m = pd.merge(t.rename(columns={'val': 'T'}), h.rename(columns={'val': 'HR'}),
                         on='ts', how='outer')
            for sh in ['Temp_patate_brut', 'Temp_patate_1_brut', 'Temp_patate1_brut']:
                tc = _read(p, sh, 'patate')
                if tc is not None:
                    m = pd.merge(m, tc.rename(columns={'val': 'Tc'}), on='ts', how='outer')
                    break
            if 'Tc' not in m:
                m['Tc'] = np.nan
            co = _read(p, 'CO2_brut', 'CO2')
            m = pd.merge(m, co.rename(columns={'val': 'CO2'}), on='ts', how='outer') \
                if co is not None else m.assign(CO2=np.nan)
            m['mode'], m['year'], m['node'] = mode, year, os.path.basename(f).replace('.xlsx', '')
            frames.append(m)
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------- nettoyage + variables derivees
def clean_and_derive(D):
    """Filtre de plausibilite physique puis calcul de VPD, Tw et potentiel evaporatif."""
    D.loc[(D['T'] < -20) | (D['T'] > 60), 'T'] = np.nan
    D.loc[(D['HR'] < 0) | (D['HR'] > 100), 'HR'] = np.nan
    D.loc[(D['Tc'] < -20) | (D['Tc'] > 60), 'Tc'] = np.nan
    D.loc[(D['CO2'] < 300) | (D['CO2'] > 5000), 'CO2'] = np.nan
    D = D.dropna(subset=['ts']).copy()

    D['hour'] = D['ts'].dt.hour
    D['periode'] = pd.cut(D['hour'], [-1, 5, 11, 17, 23], labels=POR).astype(str)

    es = 0.6108 * np.exp(17.27 * D['T'] / (D['T'] + 237.3))        # Tetens, kPa
    D['VPD'] = es * (1 - D['HR'] / 100.0)                           # Eq. 8
    T, RH = D['T'], D['HR']
    D['Tw'] = (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659))     # Stull (2011)
               + 0.00391838 * np.sqrt(RH ** 3) * np.arctan(0.023101 * RH)
               - np.arctan(RH - 1.676331) + np.arctan(T + RH) - 4.686035)
    D['PotEvap'] = D['T'] - D['Tw']
    return D


# ------------------------------------------------------------------- tableaux
def build_tables(D):
    def sub(m, y, p=None):
        d = D[(D['mode'] == m) & (D['year'] == y)]
        return d[d['periode'] == p] if p else d

    S1 = []
    for y in sorted(D['year'].unique()):
        for m in ['Frigo', 'Hu', 'Serre', 'Ext']:
            g = sub(m, y)
            if g.empty:
                continue
            T, H, V = g['T'].dropna(), g['HR'].dropna(), g['VPD'].dropna()
            Tc, Co = g['Tc'].dropna(), g['CO2'].dropna()
            v3 = sub(m, y, 'P3 (12-18h)')['VPD'].dropna()
            S1.append({'Campaign': y, 'Storage mode': LAB[m],
                       'Air T mean (C)': round(T.mean(), 1), 'Air T SD (C)': round(T.std(), 1),
                       'Air T max (C)': round(T.max(), 1),
                       'RH mean (%)': round(H.mean(), 1), 'RH SD (%)': round(H.std(), 1),
                       'VPD mean (kPa)': round(V.mean(), 2), 'VPD SD (kPa)': round(V.std(), 2),
                       'VPD 12-18 h (kPa)': round(v3.mean(), 2) if len(v3) > 20 else None,
                       'Time > 30 C (%)': round(100 * (T > 30).mean(), 1),
                       'Max tuber core T (C)': round(Tc.max(), 1) if len(Tc) > 30 else None,
                       'CO2 mean (ppm)': int(round(Co.mean())) if len(Co) > 30 else None,
                       'N records (T)': int(len(T)),
                       'Monitored days': int(g['ts'].dt.date.nunique())})
    S1 = pd.DataFrame(S1)

    S2 = []
    for y in sorted(D['year'].unique()):
        for p in POR:
            d = {'Campaign': y, 'Intra-day period': p}
            for m in ['Frigo', 'Hu', 'Serre', 'Ext']:
                g = sub(m, y, p)
                d[f'T {LAB[m]} (C)'] = round(g['T'].mean(), 1)
                d[f'RH {LAB[m]} (%)'] = round(g['HR'].mean(), 1)
                d[f'VPD {LAB[m]} (kPa)'] = round(g['VPD'].mean(), 2)
            d['dT H-Trad (C)'] = round(d['T H (C)'] - d['T Trad (C)'], 1)
            d['dRH H-Trad (pts)'] = round(d['RH H (%)'] - d['RH Trad (%)'], 1)
            d['VPD reduction H vs Trad (%)'] = round(100 * (1 - d['VPD H (kPa)'] / d['VPD Trad (kPa)']), 1)
            S2.append(d)
    S2 = pd.DataFrame(S2)

    hu = D[D['mode'] == 'Hu'].copy()
    hu['Node'] = 'N' + hu['node'].str.extract(r'noeud_(\d)')[0]
    S3 = (hu.groupby(['year', 'Node'])
            .apply(lambda g: pd.Series({
                'T mean (C)': round(g['T'].mean(), 1), 'T SD (C)': round(g['T'].std(), 1),
                'RH mean (%)': round(g['HR'].mean(), 1), 'RH SD (%)': round(g['HR'].std(), 1),
                'VPD mean (kPa)': round(g['VPD'].mean(), 2), 'N records': int(g['T'].notna().sum())}),
                   include_groups=False)
            .reset_index().rename(columns={'year': 'Campaign'}))

    S4 = pd.DataFrame([
        ('1. Raw import', 'Per-node Excel workbooks (Temperature_brut, Humidite_brut, '
                          'Temp_patate_brut, CO2_brut); Date and Heure merged into one timestamp.'),
        ('2. Physical plausibility filter', 'Air and tuber-core temperature outside [-20; 60] C, '
                          'RH outside [0; 100] %, CO2 outside [300; 5000] ppm set to missing '
                          '(sensor drop-out codes, e.g. -99 C, negative CO2).'),
        ('3. Derived variables', 'es = 0.6108*exp(17.27*T/(T+237.3)); VPD = es*(1-RH/100) [kPa]. '
                          'Wet-bulb temperature after Stull (2011).'),
        ('4. Aggregation', 'Means on cleaned instantaneous records; four fixed intra-day windows '
                          '(00-06, 06-12, 12-18, 18-24 h). No imputation applied.'),
        ('5. Known limitations', '2025 greenhouse air node shows an implausibly low diurnal '
                          'amplitude (SD = 0.9 C): the H vs Trad air comparison is anchored on 2024. '
                          'The 2025 cold-room record covers 13 June - 2 July only.'),
    ], columns=['Step', 'Description'])
    return S1, S2, S3, S4


# -------------------------------------------------------------------- figures
def figure_main(D, out):
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9, 'axes.linewidth': 0.8,
                         'axes.spines.top': False, 'axes.spines.right': False})
    sub = lambda m, y, p=None: (D[(D['mode'] == m) & (D['year'] == y) & (D['periode'] == p)]
                                if p else D[(D['mode'] == m) & (D['year'] == y)])
    fig, axs = plt.subplots(2, 2, figsize=(7.4, 6.4))

    ax = axs[0, 0]; w, x = 0.36, np.arange(3)
    for y, off, al in [(2024, -w / 2, 1.0), (2025, w / 2, 0.5)]:
        mu = [sub(m, y)['VPD'].mean() for m in ORDER]
        sd = [sub(m, y)['VPD'].std() for m in ORDER]
        ax.bar(x + off, mu, w, yerr=sd, capsize=2.5, color=[COL[m] for m in ORDER], alpha=al,
               edgecolor='black', linewidth=0.6, error_kw=dict(lw=0.7, ecolor='#444444'))
        for xi, v, s in zip(x + off, mu, sd):
            ax.text(xi, v + s + 0.10, f'{v:.2f}', ha='center', fontsize=7.2)
    ax.set_xticks(x); ax.set_xticklabels([LAB[m] for m in ORDER]); ax.set_ylim(0, 4.2)
    ax.set_ylabel('Vapour pressure deficit (kPa)')
    ax.set_title('(a) Mean VPD by storage mode', fontsize=9, loc='left', fontweight='bold')
    ax.legend(handles=[Patch(fc='#888888', ec='k', lw=.6, label='2024'),
                       Patch(fc='#888888', ec='k', lw=.6, alpha=.5, label='2025')],
              frameon=False, fontsize=7.5, loc='upper left')
    ax.text(0.98, 0.90, '7 °C < H < Trad', transform=ax.transAxes, ha='right',
            fontsize=8.5, style='italic')

    ax = axs[0, 1]
    for m in ['Frigo', 'Hu', 'Serre', 'Ext']:
        v = [sub(m, 2024, p)['VPD'].mean() for p in POR]
        e = [sub(m, 2024, p)['VPD'].sem() for p in POR]
        ax.errorbar(range(4), v, yerr=e, marker='o', ms=4, lw=1.6, color=COL[m], label=LAB[m],
                    ls='--' if m == 'Ext' else '-', capsize=2, elinewidth=.7, zorder=3)
    ax.axvspan(1.62, 2.38, color='#f7e08a', alpha=.30, zorder=0); ax.set_ylim(0, 4.3)
    ax.text(2.42, 3.95, 'hottest\nhours', ha='center', va='top', fontsize=6.8,
            style='italic', color='#8a6d3b')
    ax.annotate('', xy=(2, 1.39), xytext=(2, 3.42),
                arrowprops=dict(arrowstyle='<->', color='#2e8b57', lw=1.2))
    ax.text(2.14, 2.30, '−59 %', fontsize=8.5, color='#2e8b57', fontweight='bold')
    ax.set_xticks(range(4)); ax.set_xticklabels(PSH, fontsize=7.5); ax.set_xlim(-0.35, 3.6)
    ax.set_ylabel('VPD (kPa)')
    ax.set_title('(b) Diurnal course of VPD (2024)', fontsize=9, loc='left', fontweight='bold')
    ax.legend(frameon=False, fontsize=7.5, ncol=2, loc='upper left')

    ax = axs[1, 0]
    for m in ['Frigo', 'Hu', 'Serre', 'Ext']:
        v = [sub(m, 2024, p)['T'].mean() for p in POR]
        e = [sub(m, 2024, p)['T'].sem() for p in POR]
        ax.errorbar(range(4), v, yerr=e, marker='s', ms=4, lw=1.6, color=COL[m], label=LAB[m],
                    ls='--' if m == 'Ext' else '-', capsize=2, elinewidth=.7)
    ax.annotate('', xy=(2, 28.69), xytext=(2, 34.49),
                arrowprops=dict(arrowstyle='<->', color='#2e8b57', lw=1.2))
    ax.text(2.20, 30.6, '−5.8 °C vs Trad\n(−5.0 °C vs outdoor)', fontsize=7.2, color='#2e8b57')
    ax.set_xticks(range(4)); ax.set_xticklabels(PSH, fontsize=7.5)
    ax.set_xlim(-0.35, 3.75); ax.set_ylim(5, 40)
    ax.set_ylabel('Air temperature (°C)')
    ax.set_title('(c) Diurnal course of air temperature (2024)', fontsize=9, loc='left', fontweight='bold')
    ax.legend(frameon=False, fontsize=7.5, ncol=2, loc='center left', bbox_to_anchor=(0.0, 0.30))

    ax = axs[1, 1]
    pct = [100 * (sub(m, 2024)['T'].dropna() > 30).mean() for m in ORDER]
    ax.bar(np.arange(3), pct, 0.5, color=[COL[m] for m in ORDER], edgecolor='black', lw=.6)
    for xi, v in zip(np.arange(3), pct):
        ax.text(xi, v + 1.5, f'{v:.1f} %', ha='center', fontsize=8)
    ax.set_ylabel('Time with air T > 30 °C (%)'); ax.set_ylim(0, 62)
    ax.set_xticks(range(3)); ax.set_xticklabels([LAB[m] for m in ORDER])
    ax2 = ax.twinx(); ax2.spines['top'].set_visible(False)
    tc = [sub(m, 2024)['Tc'].max() for m in ORDER]
    ax2.plot(range(3), tc, 'D', ms=6.5, color='black', mfc='white', mew=1.3, ls='none',
             label='Max. tuber core T')
    for xi, v in zip(range(3), tc):
        ax2.text(xi + 0.14, v, f'{v:.1f} °C', fontsize=7.8, va='center', ha='left')
    ax2.set_ylabel('Max. tuber core temperature (°C)', labelpad=2); ax2.set_ylim(15, 52)
    ax2.legend(frameon=False, fontsize=7.5, loc='upper left')
    ax.set_title('(d) Thermal load on the stored lot (2024)', fontsize=9, loc='left', fontweight='bold')

    plt.tight_layout(pad=1.2)
    for ext in ('png', 'pdf'):
        plt.savefig(os.path.join(out, f'Figure_IoT_main.{ext}'), dpi=600, bbox_inches='tight')
    plt.close()


def figure_supp(D, out):
    hu = D[D['mode'] == 'Hu'].copy()
    hu['N'] = hu['node'].str.extract(r'noeud_(\d)')[0]
    fig, axs = plt.subplots(1, 2, figsize=(7.4, 3.2))

    ax = axs[0]; w, x = 0.36, np.arange(5)
    for y, off, al in [(2024, -w / 2, 1.0), (2025, w / 2, 0.5)]:
        m = [hu[(hu['N'] == str(i)) & (hu['year'] == y)]['VPD'].mean() for i in range(1, 6)]
        s = [hu[(hu['N'] == str(i)) & (hu['year'] == y)]['VPD'].sem() for i in range(1, 6)]
        ax.bar(x + off, m, w, yerr=s, capsize=2, color='#2e8b57', alpha=al,
               edgecolor='k', lw=.5, error_kw=dict(lw=.7), label=str(y))
    ref = D[(D['mode'] == 'Serre') & (D['year'] == 2024)]['VPD'].mean()
    ax.axhline(ref, ls=':', color='#c0392b', lw=1.2)
    ax.text(4.4, ref + .04, 'Trad 2024', fontsize=7, color='#c0392b', ha='right')
    ax.set_xticks(x); ax.set_xticklabels([f'N{i}' for i in range(1, 6)]); ax.set_ylim(0, 2.6)
    ax.set_xlabel('IoT node inside the humidification chamber'); ax.set_ylabel('Mean VPD (kPa)')
    ax.legend(frameon=False, fontsize=7.5)
    ax.set_title('(a) Spatial homogeneity within the H chamber', fontsize=8.8,
                 loc='left', fontweight='bold')

    ax = axs[1]; cols = [COL[m] for m in ORDER]
    for y, mk, ls in [(2024, 'o', '-'), (2025, '^', '--')]:
        v = [D[(D['mode'] == m) & (D['year'] == y)]['VPD'].mean() for m in ORDER]
        r = [LOSSES[y][m][0] / LOSSES[y][m][1] * 100 for m in ORDER]
        ax.plot(v, r, color='#999999', lw=.9, ls=ls, zorder=1)
        ax.scatter(v, r, s=70, c=cols, marker=mk, edgecolor='k', lw=.7, zorder=3)
        for vi, ri, m in zip(v, r, ORDER):
            ax.annotate(LAB[m], (vi, ri), textcoords='offset points',
                        xytext=(6, -9 if y == 2024 else 4), fontsize=7.2)
    ax.set_xlabel('Mean vapour pressure deficit (kPa)')
    ax.set_ylabel('Weight-loss rate (% per 100 d)')
    ax.legend(handles=[Line2D([], [], marker='o', ls='none', mfc='#bbbbbb', mec='k', ms=7, label='2024'),
                       Line2D([], [], marker='^', ls='none', mfc='#bbbbbb', mec='k', ms=7, label='2025')],
              frameon=False, fontsize=7.5, loc='lower right')
    ax.set_title('(b) Ordinal concordance VPD ↔ weight loss', fontsize=8.8,
                 loc='left', fontweight='bold')
    ax.set_xlim(-0.1, 2.6); ax.set_ylim(2.5, 11)

    plt.tight_layout(pad=1.1)
    for ext in ('png', 'pdf'):
        plt.savefig(os.path.join(out, f'Figure_S1_IoT.{ext}'), dpi=600, bbox_inches='tight')
    plt.close()


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='.', help='dossier des classeurs IoT bruts')
    ap.add_argument('--output', default='./sortie', help='dossier de sortie')
    a = ap.parse_args()
    os.makedirs(a.output, exist_ok=True)

    print('1/4  Chargement des classeurs IoT ...')
    D = load(a.input)
    print(f'     {len(D):,} enregistrements bruts')

    print('2/4  Nettoyage et variables derivees ...')
    D = clean_and_derive(D)
    print(f'     T valides : {D["T"].notna().sum():,} | VPD calcules : {D["VPD"].notna().sum():,}')

    print('3/4  Tableaux supplementaires ...')
    S1, S2, S3, S4 = build_tables(D)
    with pd.ExcelWriter(os.path.join(a.output, 'Supplementary_Data_IoT.xlsx'), engine='openpyxl') as w:
        S1.to_excel(w, sheet_name='Table S1 - modes', index=False)
        S2.to_excel(w, sheet_name='Table S2 - intraday', index=False)
        S3.to_excel(w, sheet_name='Table S3 - nodes', index=False)
        S4.to_excel(w, sheet_name='Table S4 - QC log', index=False)
    print(S1.to_string(index=False))

    print('4/4  Figures ...')
    figure_main(D, a.output)
    figure_supp(D, a.output)
    print(f'Termine. Sorties dans : {os.path.abspath(a.output)}')


if __name__ == '__main__':
    main()
