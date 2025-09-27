# app.py
import streamlit as st
import pandas as pd
from collections import defaultdict
import numpy_financial as npf
import numpy as np

# --- CONFIGURATION DE LA PAGE STREAMLIT ---
# Doit être la première commande Streamlit de votre script
st.set_page_config(
    page_title="Simulateur SCI à l'IS",
    page_icon="🏡",
    layout="wide"
)

# --- MOTEUR DE CALCUL DU PRÊT (repris de votre script original) ---
def generer_tableau_amortissement(montant_pret, taux_annuel_pc, duree_annees):
    if not (montant_pret > 0 and taux_annuel_pc > 0 and duree_annees > 0): return {}
    taux_mensuel = (taux_annuel_pc / 100) / 12
    nb_mois = int(duree_annees * 12)
    try:
        mensualite = montant_pret * (taux_mensuel * (1 + taux_mensuel)**nb_mois) / ((1 + taux_mensuel)**nb_mois - 1)
    except ZeroDivisionError:
        return {}
    tableau_annuel = defaultdict(lambda: {'interet': 0, 'principal': 0, 'crd_fin_annee': 0})
    capital_restant_du = montant_pret
    for mois in range(1, nb_mois + 1):
        annee = (mois - 1) // 12 + 1
        interet_mois = capital_restant_du * taux_mensuel
        principal_mois = mensualite - interet_mois
        capital_restant_du -= principal_mois
        tableau_annuel[annee]['interet'] += interet_mois; tableau_annuel[annee]['principal'] += principal_mois
        tableau_annuel[annee]['crd_fin_annee'] = capital_restant_du
    return dict(tableau_annuel)

# --- MOTEUR DE SIMULATION SCI À L'IS (repris de votre script original) ---
def generer_projection_sci_is(params):
    try:
        valeurs_num = {k: float(v) for k, v in params.items()}
    except (ValueError, TypeError):
        return [{"erreur": "Veuillez entrer des nombres valides."}]

    # --- Initialisation ---
    prix_achat, cout_travaux, frais_notaire = valeurs_num.get("prix_achat", 0), valeurs_num.get("cout_travaux", 0), valeurs_num.get("frais_notaire", 0)
    cout_acquisition = prix_achat + cout_travaux
    base_amortissable = prix_achat + cout_travaux + frais_notaire
    apport, frais_dossier = valeurs_num.get("apport_personnel", 0), valeurs_num.get("frais_dossier", 0)
    investissement_initial_personnel = apport + frais_dossier
    montant_pret = cout_acquisition + frais_notaire - apport
    duree_pret = int(valeurs_num.get("duree_pret", 0))
    tableau_amortissement_pret = generer_tableau_amortissement(montant_pret, valeurs_num.get("taux_interet_pret", 0), duree_pret)
    mensualite_assurance = (montant_pret * (valeurs_num.get("taux_assurance_pret", 0) / 100)) / 12
    loyer_mensuel_actuel, charges_copro_actuelles, taxe_fonciere_actuelle = valeurs_num.get("loyer_mensuel", 0), valeurs_num.get("charges_copro", 0), valeurs_num.get("taxe_fonciere", 0)
    inflation_pc, revalo_bien_pc = valeurs_num.get("inflation_pc", 0) / 100, valeurs_num.get("revalo_bien_pc", 0) / 100
    
    cashflow_investisseur_accumule = 0
    amortissement_cumule = 0
    tresorerie_sci_cumulee = 0
    abondement_cumule = 0
    
    flux_tresorerie_tri_annuels = []
    projection = []

    for annee in range(1, duree_pret + 1):
        if annee > 1:
            loyer_mensuel_actuel *= (1 + inflation_pc); charges_copro_actuelles *= (1 + inflation_pc); taxe_fonciere_actuelle *= (1 + inflation_pc)
        
        loyer_annuel = loyer_mensuel_actuel * 12
        charges_copro_annuelles = charges_copro_actuelles * 12
        frais_gestion_annuels = loyer_annuel * (valeurs_num.get("frais_gestion_pc", 0) / 100)
        gli_annuelle = (loyer_annuel + charges_copro_annuelles) * (valeurs_num.get("taux_gli_pc", 0) / 100)
        charges_annuelles_cash = charges_copro_annuelles + taxe_fonciere_actuelle + valeurs_num.get("assurance_pno", 0) + frais_gestion_annuels + gli_annuelle + (valeurs_num.get("cfe", 0) * ((1 + inflation_pc)**(annee - 1)))
        if annee == 1: charges_annuelles_cash += frais_dossier
        
        interets_annuels = tableau_amortissement_pret.get(annee, {}).get('interet', 0)
        principal_annuel = tableau_amortissement_pret.get(annee, {}).get('principal', 0)
        mensualite_credit_annuelle = (interets_annuels + principal_annuel) + (mensualite_assurance * 12)
        
        amort_immo_et_frais = base_amortissable * 0.85 / valeurs_num.get("duree_amort_immo", 1) if annee <= valeurs_num.get("duree_amort_immo", 0) else 0
        amort_travaux = cout_travaux / 15 if annee <= 15 else 0
        amort_meubles = valeurs_num.get("valeur_meubles", 0) / valeurs_num.get("duree_amort_meubles", 1) if annee <= valeurs_num.get("duree_amort_meubles", 0) else 0
        amortissement_annuel = amort_immo_et_frais + amort_travaux + amort_meubles
        amortissement_cumule += amortissement_annuel
        
        charges_deductibles_totales = charges_annuelles_cash + interets_annuels + (mensualite_assurance*12)
        benefice_sci_av_is = loyer_annuel - charges_deductibles_totales - amortissement_annuel

        is_a_payer = 0
        if benefice_sci_av_is > 0:
            benefice_taux_reduit = min(benefice_sci_av_is, 42500)
            is_a_payer = (benefice_taux_reduit * 0.15) + ((benefice_sci_av_is - benefice_taux_reduit) * 0.25)

        cashflow_sci_avant_is = loyer_annuel - charges_annuelles_cash - mensualite_credit_annuelle
        resultat_net_sci = benefice_sci_av_is - is_a_payer

        tresorerie_sci_avant_abondement = tresorerie_sci_cumulee + cashflow_sci_avant_is - is_a_payer
        abondement = 0
        if tresorerie_sci_avant_abondement < 0:
            abondement = abs(tresorerie_sci_avant_abondement)
            abondement_cumule += abondement
            tresorerie_sci_cumulee = 0 
        else:
            tresorerie_sci_cumulee = tresorerie_sci_avant_abondement
            
        taux_distrib = valeurs_num.get("taux_distrib_pc", 100) / 100
        dividendes_distribuables = max(0, resultat_net_sci)
        dividendes_verses = min(dividendes_distribuables, max(0, tresorerie_sci_cumulee)) * taux_distrib
        
        impot_dividendes = dividendes_verses * 0.30
        cash_net_investisseur = dividendes_verses - impot_dividendes
        cashflow_investisseur_accumule += cash_net_investisseur
        tresorerie_sci_cumulee -= dividendes_verses
        
        flux_tresorerie_tri_annuels.append(cash_net_investisseur - abondement)

        prix_revente = cout_acquisition * (1 + revalo_bien_pc)**annee
        valeur_nette_comptable = base_amortissable - amortissement_cumule
        plus_value_pro = prix_revente - valeur_nette_comptable
        
        is_sur_pv = max(0, (min(plus_value_pro, 42500) * 0.15) + (max(0, plus_value_pro - 42500) * 0.25))
        crd = tableau_amortissement_pret.get(annee, {}).get('crd_fin_annee', 0)
        
        prix_vente_net = prix_revente - crd - is_sur_pv
        
        investissement_initial_total = investissement_initial_personnel + abondement_cumule
        
        rentabilite_nette_pc = (prix_vente_net / investissement_initial_total) * 100 if investissement_initial_total > 0 else 0

        tri_pc = 0
        cash_flows_annuel = [-investissement_initial_personnel] + flux_tresorerie_tri_annuels[:]
        cash_flows_annuel[-1] += (prix_vente_net + tresorerie_sci_cumulee)

        try:
            tri = npf.irr(cash_flows_annuel)
            if not np.isnan(tri):
                tri_pc = tri * 100
        except:
            tri_pc = 0

        projection.append({
            "Année": annee, "CF SCI (av.IS)": cashflow_sci_avant_is, "Bénéfice SCI": benefice_sci_av_is, 
            "Impôt Société": is_a_payer, "Net Poche Annuel": cash_net_investisseur, 
            "Abondement": abondement, "Tréso. SCI": tresorerie_sci_cumulee,
            "Valeur Bien": prix_revente, "CRD": crd, 
            "Rentabilité Nette (%)": rentabilite_nette_pc,
            "TRI (%)": tri_pc
        })
    return projection

# --- INTERFACE UTILISATEUR (CONSTRUITE AVEC STREAMLIT) ---

st.title("Simulateur d'Investissement Locatif en SCI à l'IS 📈")
st.markdown("Un outil complet pour projeter la rentabilité de votre projet immobilier sur toute la durée du crédit.")

# --- BARRE LATÉRALE POUR LES PARAMÈTRES ---
st.sidebar.header("Paramètres de Simulation")

# Section Bien & Charges
with st.sidebar.expander("🏠 Bien & Charges", expanded=True):
    prix_achat = st.number_input("Prix d'achat (€)", min_value=0, value=200000, step=1000)
    cout_travaux = st.number_input("Coût des travaux (€)", min_value=0, value=30000, step=500)
    frais_notaire = st.number_input("Frais de notaire (€)", min_value=0, value=16000, step=100)
    loyer_mensuel = st.number_input("Loyer mensuel HC (€)", min_value=0, value=1200, step=10)
    charges_copro = st.number_input("Charges copropriété / mois (€)", min_value=0, value=100, step=5)
    taxe_fonciere = st.number_input("Taxe foncière (€)", min_value=0, value=1000, step=10)

# Section Financement
with st.sidebar.expander("🏦 Financement", expanded=True):
    apport_personnel = st.number_input("Apport personnel (€)", min_value=0, value=20000, step=500)
    duree_pret = st.number_input("Durée du prêt (années)", min_value=1, max_value=30, value=20, step=1)
    taux_interet_pret = st.number_input("Taux d'intérêt du prêt (%)", min_value=0.0, value=3.5, step=0.01, format="%.2f")
    taux_assurance_pret = st.number_input("Taux d'assurance du prêt (%)", min_value=0.0, value=0.34, step=0.01, format="%.2f")
    frais_dossier = st.number_input("Frais de dossier bancaire (€)", min_value=0, value=1500, step=50)

# Section Hypothèses & Paramètres
with st.sidebar.expander("⚙️ Hypothèses & Paramètres", expanded=False):
    inflation_pc = st.number_input("Inflation / Revalorisation loyer (%)", min_value=0.0, value=2.0, step=0.1, format="%.1f")
    revalo_bien_pc = st.number_input("Revalorisation annuelle du bien (%)", min_value=0.0, value=3.0, step=0.1, format="%.1f")
    assurance_pno = st.number_input("Assurance PNO (€/an)", min_value=0, value=200, step=10)
    frais_gestion_pc = st.number_input("Frais de gestion (%)", min_value=0.0, value=7.0, step=0.1, format="%.1f")
    taux_gli_pc = st.number_input("Taux GLI (%)", min_value=0.0, value=3.5, step=0.1, format="%.1f")
    taux_distrib_pc = st.number_input("Taux de distribution des dividendes (%)", min_value=0.0, max_value=100.0, value=100.0, step=1.0)

# Section Amortissement du Bien
with st.sidebar.expander("🧾 Amortissement & Fiscalité", expanded=False):
    duree_amort_immo = st.number_input("Durée amortissement Immobilier (ans)", min_value=1, value=30, step=1)
    valeur_meubles = st.number_input("Valeur des meubles (€)", min_value=0, value=15000, step=500)
    duree_amort_meubles = st.number_input("Durée amortissement Meubles (ans)", min_value=1, value=7, step=1)
    cfe = st.number_input("CFE (€/an)", min_value=0, value=200, step=10)


# --- AFFICHAGE DES RÉSULTATS ---
st.header("Résultats de la Simulation")

# Rassembler tous les paramètres pour le moteur de calcul
params = {
    "prix_achat": prix_achat, "cout_travaux": cout_travaux, "frais_notaire": frais_notaire,
    "loyer_mensuel": loyer_mensuel, "charges_copro": charges_copro, "taxe_fonciere": taxe_fonciere,
    "apport_personnel": apport_personnel, "duree_pret": duree_pret, "taux_interet_pret": taux_interet_pret,
    "taux_assurance_pret": taux_assurance_pret, "frais_dossier": frais_dossier,
    "inflation_pc": inflation_pc, "revalo_bien_pc": revalo_bien_pc, "assurance_pno": assurance_pno,
    "frais_gestion_pc": frais_gestion_pc, "taux_gli_pc": taux_gli_pc, "taux_distrib_pc": taux_distrib_pc,
    "duree_amort_immo": duree_amort_immo, "valeur_meubles": valeur_meubles,
    "duree_amort_meubles": duree_amort_meubles, "cfe": cfe
}

# Lancer la projection
projection_data = generer_projection_sci_is(params)

if "erreur" in projection_data[0]:
    st.error(f"Une erreur est survenue : {projection_data[0]['erreur']}")
else:
    # Convertir les résultats en DataFrame Pandas pour un meilleur affichage
    df = pd.DataFrame(projection_data)
    
    # Formater les colonnes pour une meilleure lisibilité
    colonnes_euros = ["CF SCI (av.IS)", "Bénéfice SCI", "Impôt Société", "Net Poche Annuel", 
                      "Abondement", "Tréso. SCI", "Valeur Bien", "CRD"]
    
    df_formate = df.style.format({col: "{:,.0f} €".format for col in colonnes_euros}) \
                        .format({"Rentabilité Nette (%)": "{:.1f}%", "TRI (%)": "{:.1f}%"}) \
                        .set_properties(**{'text-align': 'right'})

    st.dataframe(df_formate, use_container_width=True)
    
    st.info("💡 Cliquez sur les en-têtes de colonnes pour trier. Utilisez la barre de défilement en bas du tableau pour voir toutes les colonnes.", icon="ℹ️")

    # Afficher quelques indicateurs clés
    st.header("Indicateurs Clés du Projet")
    montant_pret = prix_achat + cout_travaux + frais_notaire - apport_personnel
    cashflow_moyen_investisseur = df["Net Poche Annuel"].mean() / 12 if not df.empty else 0
    tri_final = df["TRI (%)"].iloc[-1] if not df.empty else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("Montant du Prêt", f"{montant_pret:,.0f} €")
    col2.metric("Cashflow Investisseur Moyen / mois", f"{cashflow_moyen_investisseur:,.0f} €")
    col3.metric(f"TRI à {duree_pret} ans", f"{tri_final:.1f}%")