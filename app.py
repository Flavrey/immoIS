# simulateur_sci_is_v18_streamlit.py
#
# Pour l'exécuter :
# 1. Assurez-vous d'avoir les bibliothèques :
#    pip install streamlit pandas numpy numpy-financial
# 2. Lancez depuis votre terminal :
#    streamlit run simulateur_sci_is_v18_streamlit.py

import streamlit as st
import pandas as pd
import numpy as np
import numpy_financial as npf
from collections import defaultdict

# --- MOTEUR DE CALCUL IMPÔT PLUS-VALUE (Particuliers, pour Scénario 2) ---
# (Inchangé)
def calculer_impot_plus_value(plus_value_brute, duree_detention):
    if plus_value_brute <= 0: return 0, 0
    abattement_ir = 0
    if duree_detention > 5:
        abattement_ir += sum(0.06 for _ in range(6, min(duree_detention, 21) + 1))
        if duree_detention >= 22: abattement_ir += 0.04
    base_imposable_ir = plus_value_brute * (1 - abattement_ir)
    impot_sur_revenu_pv = base_imposable_ir * 0.19
    abattement_ps = 0
    if duree_detention > 5:
        abattement_ps += sum(0.0165 for _ in range(6, min(duree_detention, 21) + 1))
        if duree_detention == 22: abattement_ps += 0.0160
        if duree_detention > 22: abattement_ps += sum(0.09 for _ in range(23, min(duree_detention, 30) + 1))
    base_imposable_ps = plus_value_brute * (1 - abattement_ps)
    prelevements_sociaux_pv = base_imposable_ps * 0.172
    impot_total_pv = max(0, impot_sur_revenu_pv) + max(0, prelevements_sociaux_pv)
    return impot_total_pv, plus_value_brute

# --- MOTEUR DE CALCUL DU PRÊT (Inchangé) ---
def generer_tableau_amortissement(montant_pret, taux_annuel_pc, duree_annees):
    if not (montant_pret > 0 and taux_annuel_pc > 0 and duree_annees > 0): return {}
    taux_mensuel = (taux_annuel_pc / 100) / 12
    nb_mois = int(duree_annees * 12)
    try:
        mensualite = npf.pmt(taux_mensuel, nb_mois, -montant_pret)
    except (ZeroDivisionError, ValueError):
        return {}
    tableau_annuel = defaultdict(lambda: {'interet': 0, 'principal': 0, 'crd_fin_annee': 0})
    capital_restant_du = montant_pret
    for mois in range(1, nb_mois + 1):
        annee = (mois - 1) // 12 + 1
        interet_mois = capital_restant_du * taux_mensuel
        principal_mois = mensualite - interet_mois
        capital_restant_du -= principal_mois
        tableau_annuel[annee]['interet'] += interet_mois
        tableau_annuel[annee]['principal'] += principal_mois
        tableau_annuel[annee]['crd_fin_annee'] = capital_restant_du if capital_restant_du > 0.01 else 0
    return dict(tableau_annuel)

# --- MOTEUR DE SIMULATION SCI À L'IS (ADAPTÉ POUR STREAMLIT) ---
def generer_projection_sci_is(params):
    """
    Génère la projection financière.
    MODIFIÉ : Accepte des nombres (float/int) en entrée et retourne
    un dictionnaire de nombres bruts (non formatés) pour affichage
    dans un DataFrame Pandas.
    """
    try:
        # Streamlit envoie des nombres, pas des strings.
        valeurs_num = params.copy()
        is_gerant_majoritaire = valeurs_num.pop("is_gerant_majoritaire", False)
    except (ValueError, TypeError):
        return [{"erreur": "Veuillez entrer des nombres valides."}]

    # --- Initialisation des valeurs de base ---
    prix_achat = valeurs_num.get("prix_achat", 0)
    cout_travaux = valeurs_num.get("cout_travaux", 0)
    frais_notaire = valeurs_num.get("frais_notaire", 0)
    valeur_meubles = valeurs_num.get("valeur_meubles", 0)
    
    # --- NOUVEAU: Distinction Capital Social / Apport en CCA (M1) ---
    capital_social = valeurs_num.get("capital_social", 0)
    apport_cca = valeurs_num.get("apport_personnel", 0) # Traité comme apport initial en CCA
    frais_dossier = valeurs_num.get("frais_dossier", 0)
    
    cout_acquisition = prix_achat + cout_travaux
    
    # --- CORRIGÉ: Base d'amortissement (C1) ---
    part_terrain_pc = valeurs_num.get("part_terrain_pc", 0) / 100
    base_amort_immo_frais = (prix_achat * (1 - part_terrain_pc)) + frais_notaire
    base_vnc_globale = prix_achat + cout_travaux + frais_notaire + valeur_meubles # Base pour calcul VNC

    # --- MIS À JOUR: Investissement et Prêt (M1) ---
    investissement_initial_personnel = apport_cca + capital_social + frais_dossier # Total cash out investisseur
    montant_pret = cout_acquisition + frais_notaire - apport_cca - capital_social
    
    duree_pret = int(valeurs_num.get("duree_pret", 0))
    if duree_pret <= 0: duree_pret = 1 # Evite division par zéro
        
    tableau_amortissement_pret = generer_tableau_amortissement(montant_pret, valeurs_num.get("taux_interet_pret", 0), duree_pret)
    mensualite_assurance = (montant_pret * (valeurs_num.get("taux_assurance_pret", 0) / 100)) / 12
    
    loyer_mensuel_base = valeurs_num.get("loyer_mensuel", 0)
    charges_copro_base = valeurs_num.get("charges_copro", 0)
    taxe_fonciere_base = valeurs_num.get("taxe_fonciere", 0)
    
    inflation_pc = valeurs_num.get("inflation_pc", 0) / 100
    revalo_bien_pc = valeurs_num.get("revalo_bien_pc", 0) / 100
    
    # --- NOUVEAU: Variables d'état (M1) ---
    solde_cca = apport_cca
    
    cashflow_investisseur_accumule = 0
    amortissement_cumule = 0
    tresorerie_sci_cumulee = 0
    abondement_cumule = 0 # Ne traque que les NOUVEAUX abondements post-initiaux
    flux_tresorerie_tri_annuels = []
    projection = []
    
    # Simule pour 25 ans après le crédit pour voir le long terme
    duree_simulation_totale = duree_pret + 25 
    
    # Définition des colonnes pour la séparation (NA)
    colonnes_projection = [
        "Année", "Loyers Annuels", "Résultat Exploitation", "IS Exploitation", 
        "Cash-flow Investisseur", "Tréso. SCI", "Solde CCA", "PV Imposable", 
        "IS sur PV", "Bénéfice Net (Immeuble)", "TRI (Immeuble) (%)",
        "Bénéfice Net (Parts)", "TRI (Parts) (%)"
    ]

    # --- Boucle principale de simulation ---
    for annee in range(1, duree_simulation_totale + 1):
        
        is_pendant_credit = (annee <= duree_pret)
        facteur_inflation = (1 + inflation_pc)**(annee - 1)
        
        # --- NOUVEAU: Vacance locative (R1) ---
        taux_occupation = valeurs_num.get("taux_occupation_pc", 100) / 100
        loyer_annuel = (loyer_mensuel_base * 12) * facteur_inflation * taux_occupation
        
        charges_copro_annuelles = (charges_copro_base * 12) * facteur_inflation
        taxe_fonciere_actuelle = taxe_fonciere_base * facteur_inflation
        
        frais_gestion_annuels = loyer_annuel * (valeurs_num.get("frais_gestion_pc", 0) / 100)
        gli_annuelle = (loyer_annuel + charges_copro_annuelles) * (valeurs_num.get("taux_gli_pc", 0) / 100)
        
        # --- NOUVEAU: Provision Gros Travaux (R2) ---
        prix_revente = cout_acquisition * (1 + revalo_bien_pc)**annee
        provision_gros_travaux_pc = valeurs_num.get("provision_gros_travaux_pc", 0) / 100
        provision_gros_travaux_annuelle = prix_revente * provision_gros_travaux_pc
        
        charges_annuelles_cash = (charges_copro_annuelles + taxe_fonciere_actuelle + 
                                  valeurs_num.get("assurance_pno", 0) + frais_gestion_annuels + gli_annuelle + 
                                  (valeurs_num.get("cfe", 0) * facteur_inflation) +
                                  provision_gros_travaux_annuelle) # Ajout de la provision au cash out
        
        if annee == 1: 
            charges_annuelles_cash += frais_dossier
        
        interets_annuels = tableau_amortissement_pret.get(annee, {}).get('interet', 0) if is_pendant_credit else 0
        principal_annuel = tableau_amortissement_pret.get(annee, {}).get('principal', 0) if is_pendant_credit else 0
        assurance_annuelle = mensualite_assurance * 12 if is_pendant_credit else 0
        mensualite_credit_annuelle = interets_annuels + principal_annuel + assurance_annuelle
        
        # --- CORRIGÉ: Calcul amortissement (C1) ---
        duree_amort_immo = max(1, valeurs_num.get("duree_amort_immo", 1))
        duree_amort_travaux = max(1, valeurs_num.get("duree_amort_travaux", 1))
        duree_amort_meubles = max(1, valeurs_num.get("duree_amort_meubles", 1))

        amort_immo_et_frais = base_amort_immo_frais / duree_amort_immo if annee <= duree_amort_immo else 0
        amort_travaux = cout_travaux / duree_amort_travaux if annee <= duree_amort_travaux else 0
        amort_meubles = valeur_meubles / duree_amort_meubles if annee <= duree_amort_meubles else 0
        
        amortissement_annuel = amort_immo_et_frais + amort_travaux + amort_meubles
        amortissement_cumule += amortissement_annuel
        
        # --- CORRIGÉ: Provision non-déductible (R2) ---
        charges_deductibles_totales = (charges_annuelles_cash - provision_gros_travaux_annuelle) + interets_annuels + assurance_annuelle
        
        # --- CORRIGÉ: IS sur Exploitation (C2) ---
        resultat_fiscal_exploitation = loyer_annuel - charges_deductibles_totales - amortissement_annuel

        is_exploitation = 0
        if resultat_fiscal_exploitation > 0:
            benefice_taux_reduit = min(resultat_fiscal_exploitation, 42500)
            is_exploitation = (benefice_taux_reduit * 0.15) + (max(0, resultat_fiscal_exploitation - benefice_taux_reduit) * 0.25)

        resultat_net_comptable = resultat_fiscal_exploitation - is_exploitation # Base pour dividendes

        # --- MIS À JOUR: Logique de Trésorerie et CCA (M1) ---
        cashflow_sci_avant_is = loyer_annuel - charges_annuelles_cash - mensualite_credit_annuelle
        tresorerie_sci_avant_operations = tresorerie_sci_cumulee + cashflow_sci_avant_is - is_exploitation
        
        abondement = 0
        if tresorerie_sci_avant_operations < 0:
            abondement = abs(tresorerie_sci_avant_operations)
            abondement_cumule += abondement
            solde_cca += abondement # L'abondement augmente le CCA
            tresorerie_sci_cumulee = 0 
        else:
            tresorerie_sci_cumulee = tresorerie_sci_avant_operations
            
        # --- MIS À JOUR: Logique de Distribution (Priorité CCA) (M1 & M2) ---
        tresorerie_disponible = tresorerie_sci_cumulee
        
        # 1. Remboursement CCA (Prioritaire, non fiscalisé)
        remboursement_cca = min(tresorerie_disponible, solde_cca)
        tresorerie_disponible -= remboursement_cca
        solde_cca -= remboursement_cca
        
        # 2. Distribution de Dividendes (Secondaire, fiscalisé)
        dividendes_distribuables = max(0, resultat_net_comptable)
        taux_distrib = valeurs_num.get("taux_distrib_pc", 100) / 100
        dividendes_potentiels = min(dividendes_distribuables, tresorerie_disponible)
        dividendes_verses = dividendes_potentiels * taux_distrib
        
        tresorerie_sci_cumulee = tresorerie_disponible - dividendes_verses
        
        # 3. Calcul Impôt sur Dividendes (Logique Gérant Majoritaire) (M2)
        impot_dividendes = 0
        if dividendes_verses > 0:
            solde_cca_pour_seuil = solde_cca + remboursement_cca
            if is_gerant_majoritaire:
                seuil_10_pc = (capital_social + solde_cca_pour_seuil) * 0.10 
                dividendes_charges_sociales = max(0, dividendes_verses - seuil_10_pc)
                dividendes_pfu = dividendes_verses - dividendes_charges_sociales
                impot_part_pfu = dividendes_pfu * 0.30
                taux_charges_sociales_tns = 0.45 # Simplification
                charges_sociales_part_cs = dividendes_charges_sociales * taux_charges_sociales_tns
                ir_part_cs = dividendes_charges_sociales * 0.128
                impot_dividendes = impot_part_pfu + charges_sociales_part_cs + ir_part_cs
            else:
                impot_dividendes = dividendes_verses * 0.30
        
        cash_net_investisseur_annuel = (dividendes_verses - impot_dividendes) + remboursement_cca - abondement
        cashflow_investisseur_accumule += cash_net_investisseur_annuel
        flux_tresorerie_tri_annuels.append(cash_net_investisseur_annuel)

        # --- SCÉNARIO 1: REVENTE IMMEUBLE (ASSET DEAL) (Corrigé C2, M1) ---
        valeur_nette_comptable = base_vnc_globale - amortissement_cumule
        plus_value_pro = max(0, prix_revente - valeur_nette_comptable)
        resultat_fiscal_total_revente = resultat_fiscal_exploitation + plus_value_pro
        
        is_total_revente = 0
        if resultat_fiscal_total_revente > 0:
             benefice_taux_reduit = min(resultat_fiscal_total_revente, 42500)
             is_total_revente = (benefice_taux_reduit * 0.15) + (max(0, resultat_fiscal_total_revente - benefice_taux_reduit) * 0.25)
        
        is_sur_pv = max(0, is_total_revente - is_exploitation)
        crd = tableau_amortissement_pret.get(annee, {}).get('crd_fin_annee', 0) if is_pendant_credit else 0
        
        cash_revente_in_sci = prix_revente - crd - is_sur_pv
        tresorerie_sci_avant_distrib_annee_N = tresorerie_sci_avant_operations if tresorerie_sci_avant_operations > 0 else 0
        tresorerie_totale_finale = tresorerie_sci_avant_distrib_annee_N + cash_revente_in_sci
        
        solde_cca_debut_annee_N = solde_cca + remboursement_cca
        remboursement_cca_final = min(tresorerie_totale_finale, solde_cca_debut_annee_N)
        tresorerie_totale_finale -= remboursement_cca_final
        remboursement_capital_social = min(tresorerie_totale_finale, capital_social)
        tresorerie_totale_finale -= remboursement_capital_social
        
        boni_de_liquidation = max(0, tresorerie_totale_finale)
        impot_boni = boni_de_liquidation * 0.30
        
        cash_net_final_investisseur_immo = remboursement_cca_final + remboursement_capital_social + (boni_de_liquidation - impot_boni)
        
        total_cash_investi = investissement_initial_personnel + abondement_cumule
        cash_accumule_annee_N_moins_1 = cashflow_investisseur_accumule - cash_net_investisseur_annuel
        total_cash_recu_immo = cash_accumule_annee_N_moins_1 + cash_net_final_investisseur_immo
        benefice_net_total_immo = total_cash_recu_immo - total_cash_investi

        cash_flows_tri_immo = [-investissement_initial_personnel] + flux_tresorerie_tri_annuels[:-1]
        flux_annee_N_immo = cash_net_final_investisseur_immo - (abondement if abondement > 0 else 0)
        cash_flows_tri_immo.append(flux_annee_N_immo)
        try:
            tri_immo = npf.irr(cash_flows_tri_immo)
            tri_pc_immo = tri_immo * 100 if not np.isnan(tri_immo) else 0
        except:
            tri_pc_immo = 0

        # --- SCÉNARIO 2: REVENTE DES PARTS (SHARE DEAL) (Nouveau M3) ---
        prix_cession_parts = prix_revente + tresorerie_sci_avant_distrib_annee_N - crd
        cout_acquisition_parts = capital_social + apport_cca + abondement_cumule
        plus_value_sur_parts = max(0, prix_cession_parts - cout_acquisition_parts)
        impot_pv_parts, _ = calculer_impot_plus_value(plus_value_sur_parts, annee) 
        
        cash_net_final_investisseur_parts = prix_cession_parts - impot_pv_parts
        total_cash_recu_parts = cash_accumule_annee_N_moins_1 + cash_net_final_investisseur_parts
        benefice_net_total_parts = total_cash_recu_parts - total_cash_investi
        
        cash_flows_tri_parts = [-investissement_initial_personnel] + flux_tresorerie_tri_annuels[:-1]
        flux_annee_N_parts = cash_net_final_investisseur_parts - (abondement if abondement > 0 else 0)
        cash_flows_tri_parts.append(flux_annee_N_parts)
        try:
            tri_parts = npf.irr(cash_flows_tri_parts)
            tri_pc_parts = tri_parts * 100 if not np.isnan(tri_parts) else 0
        except:
            tri_pc_parts = 0

        # --- MODIFIÉ: Ajout des données BRUTES (nombres) ---
        
        # Ligne de séparation (NA)
        if annee == duree_pret + 1 and duree_pret > 0:
             projection.append({key: pd.NA for key in colonnes_projection})

        projection.append({
            "Année": f"An {annee}" if annee == duree_pret + 1 else annee,
            "Loyers Annuels": loyer_annuel,
            "Résultat Exploitation": resultat_fiscal_exploitation,
            "IS Exploitation": is_exploitation,
            "Cash-flow Investisseur": cash_net_investisseur_annuel,
            "Tréso. SCI": tresorerie_sci_cumulee,
            "Solde CCA": solde_cca,
            "PV Imposable": plus_value_pro,
            "IS sur PV": is_sur_pv,
            "Bénéfice Net (Immeuble)": benefice_net_total_immo,
            "TRI (Immeuble) (%)": tri_pc_immo,
            "Bénéfice Net (Parts)": benefice_net_total_parts,
            "TRI (Parts) (%)": tri_pc_parts
        })

    return projection

# --- Dictionnaire des descriptions (Inchangé) ---
descriptions_calcul = {
    "Année": "L'année de la simulation. 'An X' marque la première année post-crédit.",
    "Loyers Annuels": "Total des loyers bruts perçus, après déduction de la vacance locative.",
    "Résultat Exploitation": "Base de calcul de l'IS : Loyers - Toutes les charges déductibles (y compris intérêts, assurances, hors provision gros travaux) - Amortissements.",
    "IS Exploitation": "Impôt sur les Sociétés payé par la SCI sur son Résultat d'Exploitation (15%/25%).",
    "Cash-flow Investisseur": "Argent net reçu par l'investisseur : (Remboursement de CCA) + (Dividendes versés - Impôts sur dividendes) - (Abondement en CCA).",
    "Tréso. SCI": "Trésorerie restante dans la SCI en fin d'année après toutes opérations (charges, IS, distrib...).",
    "Solde CCA": "Solde du Compte Courant d'Associé. Ce que la SCI vous 'doit'. Augmente avec les apports/abondements, diminue avec les remboursements.",
    "PV Imposable": "Plus-value professionnelle (Vente Immeuble) : Prix de Vente - Valeur Nette Comptable (VNC).",
    "IS sur PV": "Part de l'Impôt sur les Sociétés (IS) attribuable à la Plus-Value (Vente Immeuble).",
    "Bénéfice Net (Immeuble)": "Enrichissement net final (Vente Immeuble) : (Total Cash Reçu) - (Total Cash Investi). Inclut le boni de liquidation taxé.",
    "TRI (Immeuble) (%)": "Taux de Rentabilité Interne de la stratégie 'Vente Immeuble' (Asset Deal).",
    "Bénéfice Net (Parts)": "Enrichissement net final (Vente des Parts) : (Total Cash Reçu) - (Total Cash Investi).",
    "TRI (Parts) (%)": "Taux de Rentabilité Interne de la stratégie 'Vente des Parts' (Share Deal). Fiscalité des particuliers."
}

# --- INTERFACE GRAPHIQUE STREAMLIT ---
def main():
    st.set_page_config(layout="wide", page_title="Simulateur SCI à l'IS")
    st.title("Simulateur d'Investissement - SCI à l'IS (v18) 📈")
    
    # --- Panneau Latéral (Sidebar) pour les entrées ---
    st.sidebar.title("Paramètres d'Entrée")
    
    with st.sidebar:
        st.subheader("Projet & Financement 🏦")
        prix_achat = st.number_input("Prix d'achat", min_value=0.0, value=200000.0, step=5000.0, format="%.0f")
        cout_travaux = st.number_input("Coût travaux", min_value=0.0, value=30000.0, step=1000.0, format="%.0f")
        valeur_meubles = st.number_input("Valeur meubles", min_value=0.0, value=15000.0, step=500.0, format="%.0f")
        frais_notaire = st.number_input("Frais notaire", min_value=0.0, value=16000.0, step=500.0, format="%.0f")
        frais_dossier = st.number_input("Frais dossier", min_value=0.0, value=1500.0, step=100.0, format="%.0f")
        capital_social = st.number_input("Capital social", min_value=0.0, value=1000.0, step=100.0, format="%.0f")
        apport_personnel = st.number_input("Apport en CCA initial", min_value=0.0, value=20000.0, step=1000.0, format="%.0f")
        duree_pret = st.number_input("Durée prêt (années)", min_value=1, max_value=30, value=20, step=1, format="%d")
        taux_interet_pret = st.number_input("Taux intérêt prêt (%)", min_value=0.0, value=3.5, step=0.1, format="%.2f")
        taux_assurance_pret = st.number_input("Taux assurance prêt (%)", min_value=0.0, value=0.34, step=0.01, format="%.2f")

        # Affichage dynamique du montant du prêt
        montant_pret_calcule = prix_achat + cout_travaux + frais_notaire - apport_personnel - capital_social
        st.metric(label="Montant du Prêt Calculé", value=f"{montant_pret_calcule:,.2f} €")

        st.subheader("Exploitation & Charges 🧾")
        loyer_mensuel = st.number_input("Loyer mensuel", min_value=0.0, value=1200.0, step=50.0, format="%.0f")
        taux_occupation_pc = st.number_input("Taux d'occupation (%)", min_value=0.0, max_value=100.0, value=95.0, step=1.0, format="%.0f")
        charges_copro = st.number_input("Charges copro (mensuelles)", min_value=0.0, value=100.0, step=10.0, format="%.0f")
        taxe_fonciere = st.number_input("Taxe foncière (annuelle)", min_value=0.0, value=1000.0, step=50.0, format="%.0f")
        frais_gestion_pc = st.number_input("Frais gestion (%)", min_value=0.0, max_value=100.0, value=7.0, step=0.5, format="%.1f")
        taux_gli_pc = st.number_input("Taux GLI (%)", min_value=0.0, max_value=100.0, value=3.5, step=0.1, format="%.1f")
        assurance_pno = st.number_input("Assurance PNO (annuelle)", min_value=0.0, value=200.0, step=10.0, format="%.0f")
        cfe = st.number_input("CFE (annuelle)", min_value=0.0, value=200.0, step=10.0, format="%.0f")
        provision_gros_travaux_pc = st.number_input("Prov. gros travaux (% val. bien)", min_value=0.0, value=0.5, step=0.1, format="%.2f")

        st.subheader("Fiscalité & Hypothèses 🧠")
        duree_amort_immo = st.number_input("Durée amort. immo (ans)", min_value=1, value=30, step=1, format="%d")
        duree_amort_travaux = st.number_input("Durée amort. travaux (ans)", min_value=1, value=15, step=1, format="%d")
        duree_amort_meubles = st.number_input("Durée amort. meubles (ans)", min_value=1, value=7, step=1, format="%d")
        part_terrain_pc = st.number_input("Part terrain (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0, format="%.0f")
        taux_distrib_pc = st.number_input("Taux distrib. dividendes (%)", min_value=0.0, max_value=100.0, value=100.0, step=5.0, format="%.0f")
        inflation_pc = st.number_input("Inflation (%)", min_value=0.0, value=2.0, step=0.1, format="%.1f")
        revalo_bien_pc = st.number_input("Revalo. bien (%)", min_value=0.0, value=3.0, step=0.1, format="%.1f")
        is_gerant_majoritaire = st.checkbox("Gérant Majoritaire (impact CS)", value=False)
        
    # --- Collecte des paramètres pour le moteur ---
    params = {
        "prix_achat": prix_achat, "cout_travaux": cout_travaux, "valeur_meubles": valeur_meubles,
        "frais_notaire": frais_notaire, "frais_dossier": frais_dossier, "capital_social": capital_social,
        "apport_personnel": apport_personnel, "duree_pret": duree_pret, "taux_interet_pret": taux_interet_pret,
        "taux_assurance_pret": taux_assurance_pret, "loyer_mensuel": loyer_mensuel,
        "taux_occupation_pc": taux_occupation_pc, "charges_copro": charges_copro,
        "taxe_fonciere": taxe_fonciere, "frais_gestion_pc": frais_gestion_pc, "taux_gli_pc": taux_gli_pc,
        "assurance_pno": assurance_pno, "cfe": cfe, "provision_gros_travaux_pc": provision_gros_travaux_pc,
        "duree_amort_immo": duree_amort_immo, "duree_amort_travaux": duree_amort_travaux,
        "duree_amort_meubles": duree_amort_meubles, "part_terrain_pc": part_terrain_pc,
        "taux_distrib_pc": taux_distrib_pc, "inflation_pc": inflation_pc, "revalo_bien_pc": revalo_bien_pc,
        "is_gerant_majoritaire": is_gerant_majoritaire
    }

    # --- Lancement de la simulation ---
    projection_data = generer_projection_sci_is(params)

    # --- Affichage des résultats ---
    if not projection_data:
        st.warning("Aucune donnée générée. Vérifiez les paramètres.")
    elif "erreur" in projection_data[0]:
        st.error(f"Erreur dans le calcul : {projection_data[0]['erreur']}")
    else:
        df = pd.DataFrame(projection_data)
        
        # --- Formatage et Style du DataFrame ---
        colonnes_euro = [
            "Loyers Annuels", "Résultat Exploitation", "IS Exploitation", 
            "Cash-flow Investisseur", "Tréso. SCI", "Solde CCA", "PV Imposable", 
            "IS sur PV", "Bénéfice Net (Immeuble)", "Bénéfice Net (Parts)"
        ]
        colonnes_pc = ["TRI (Immeuble) (%)", "TRI (Parts) (%)"]
        
        format_dict = {col: "€ {:,.0f}" for col in colonnes_euro}
        format_dict.update({col: "{:.1f} %" for col in colonnes_pc})
        
        def style_special_rows(row):
            """Met en surbrillance les lignes 'An X' et 'Séparateur'."""
            style = [''] * len(row)
            if str(row['Année']).startswith('An'):
                style = ['background-color: #E8F5E9; font-weight: bold;'] * len(row)
            elif pd.isna(row['Année']):
                # Crée une ligne de séparation visuelle
                style = ['background-color: #f0f2f6; color: #f0f2f6; border-top: 1px solid #ddd; border-bottom: 1px solid #ddd;'] * len(row)
            return style

        st.subheader("Projection Financière Annuelle & Scénarios de Sortie")
        st.dataframe(
            df.style.apply(style_special_rows, axis=1)
                    .format(format_dict, na_rep="---"), # Applique format € et %
            use_container_width=True, # Occupe toute la largeur
            height=(35 * (len(df) + 1)) + 2 # Hauteur dynamique
        )

        # --- Glossaire des colonnes ---
        st.subheader("Glossaire des Colonnes")
        with st.expander("Cliquez pour afficher les définitions des colonnes"):
            for col_name, description in descriptions_calcul.items():
                st.markdown(f"**{col_name}** : {description}")

if __name__ == "__main__":
    main()
