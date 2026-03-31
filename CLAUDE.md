# AquaTogo — Contexte projet

Application web interne de gestion pour une boutique aquariophile (Togo).
**Pas un e-commerce public.** Outil métier pour un ou plusieurs vendeurs.

## Stack technique

- **Backend** : Django 6 + PostgreSQL
- **Frontend** : Django Templates + Tailwind CSS v3 + Alpine.js (CDN)
- **Pas de** React, DRF, ni API publique
- **Fichiers statiques** : WhiteNoise (prod) + `npm run dev` pour compiler Tailwind
- **Images produits** : Pillow, stockées dans `media/`

## Lancer le projet

```bash
# Backend
python manage.py runserver

# CSS (watch)
npm run dev

# CSS (prod)
npm run build
```

## Structure des apps

| App | Rôle |
|-----|------|
| `core` | Auth, dashboard, UserProfile |
| `products` | Produits (poissons & accessoires), stock |
| `services` | Prestations d'entretien, renouvellement |
| `clients` | Clients, dettes, rappels |
| `sales` | Ventes (Sale + SaleItem + Payment) |
| `accounting` | Dépenses (Expense) |

## Modèles clés

### products.Product
- `category` : `fish` | `accessory`
- `image` : ImageField optionnel → `media/products/`
- `margin`, `margin_percent`, `is_low_stock`, `is_out_of_stock` : propriétés calculées
- `decrease_stock(qty)` / `increase_stock(qty)` : méthodes métier

### services.Service + ServiceExecution
- `renewal_delay_days` nullable → ponctuel si None
- `ServiceExecution.next_due_date` = `execution_date + renewal_delay_days` (auto dans `save()`)
- `reminder_sent` : prêt pour intégration Telegram (future)

### sales.Sale + SaleItem + Payment
- `Sale.recompute_totals()` : recalcule depuis les SaleItems
- `Sale.update_payment_status()` : appelé automatiquement par `Payment.save()`
- `SaleItem.save()` : snapshote les prix + décrémente le stock si produit
- `payment_status` : `unpaid` | `partial` | `paid`

### clients.Client
- `outstanding_balance` : propriété calculée (total facturé − total payé)
- `upcoming_service_executions(days=30)` : rappels à venir

### accounting.Expense
- Catégories : `stock` | `transport` | `equipment` | `utilities` | `other`

### core.UserProfile
- Extension de User Django : champ `phone`
- Créé automatiquement via signal `post_save`

## URLs actives

| URL | Vue | Nom |
|-----|-----|-----|
| `/` | Dashboard | `core:dashboard` |
| `/login/` | Login | `core:login` |
| `/logout/` | Logout (POST) | `core:logout` |
| `/profil/` | Profil utilisateur | `core:profile` |
| `/admin/` | Django admin | — |

Les URLs des autres apps (`products:list`, `sales:list`, etc.) sont en `#` dans la sidebar —
**à câbler au fur et à mesure du développement des vues.**

## Templates

```
templates/
  base.html                    ← layout principal (sidebar + topbar mobile)
  partials/
    _sidebar_content.html      ← navigation + utilisateur connecté
  auth/
    login.html                 ← page standalone (hors base.html)
    profile.html
  core/
    dashboard.html
```

## Conventions importantes

- **Montants** : toujours `DecimalField`, affichés en **FCFA**
- **`format_html()`** : uniquement si la chaîne contient au moins un `{}` — sinon retourner une string Python simple (Django 6 lève une TypeError sinon)
- **Logout** : Django 6 exige un POST — utiliser un `<form method="post">` dans la sidebar
- **Sidebar links** : tant qu'une app n'a pas son `urls.py`, le lien reste `href="#"`
- **Mobile-first** : toutes les vues pensées d'abord pour mobile

## Fichiers de config notables

| Fichier | Rôle |
|---------|------|
| `config/settings.py` | `LOGIN_URL`, `MEDIA_ROOT`, `STATIC_ROOT` |
| `config/urls.py` | Inclut `core.urls` + media en DEBUG |
| `tailwind.config.js` | Scanne `templates/**/*.html` |
| `static/css/input.css` | Directives Tailwind + composants (`.btn-primary`, `.card`, `.badge-*`, `.nav-link`) |
| `package.json` | Scripts `dev` / `build` pour Tailwind |

## Logo

`static/img/logo.png` — poisson bleu AquaTogo (à placer manuellement).


Voici ci dessous, la description fonctionnelle de mon projet: # 📌 PROJET : AquaTogo **Domaine : Vente de produits d’aquarium & prestations d’entretien** --- # 🎯 1️⃣ Objectif du projet Développer une **application web mobile-first**, utilisable : - 📱 En priorité sur smartphone (Android / iPhone) - 💻 Aussi sur ordinateur (PC) - 🌐 Accessible via navigateur (pas besoin d’installer) Cela signifie : - Interface optimisée pour petit écran - Boutons larges et simples - Navigation rapide - Création de vente en quelques clics - Chargement rapide même avec connexion moyenne Technologie recommandée côté interface : - Django + Templates responsives Développer une **application web professionnelle** permettant : - La gestion du stock - La gestion des ventes (produits & services) - La gestion des clients - Le suivi des bénéfices - Une mini-comptabilité adaptée au métier - L’envoi automatique d’un résumé des ventes via Telegram --- # 🧩 2️⃣ Fonctionnalités principales ## 📦 A. Gestion des produits (Aquarium) - Création / modification produits - Prix d’achat - Prix de vente - Marge automatique - Gestion du stock en temps réel - Alerte stock faible --- ## 🛠 B. Gestion des prestations (Entretien) - Création de services (nettoyage, installation, maintenance) - Tarification - Historique des prestations par client - Alerte si un entretien va atteindre depasse 2 semaine pour la renouveler --- ## 🧍 C. Gestion des clients - Nom - Numéro de téléphone - Historique des achats - Historique des prestations - Montant total dépensé - Possibilité de contact via WhatsApp - Montrer les clients qui doivent de l'argent --- ## 🧾 D. Gestion des ventes - Vente de produits - Facturation PDF - Vente de services - Détail par ligne - Filtrage : - Par jour - Par semaine - Par mois - Impression facture (optionnel futur) --- ## 📊 E. Tableau de bord (Dashboard) - Total ventes du jour - Total ventes du mois - Répartition Produits / Services - Bénéfice estimé - Produits les plus vendus --- ## 💰 F. Mini comptabilité - Revenus produits - Revenus services - Dépenses (achat stock, transport, matériel…) - Calcul automatique : - Bénéfice brut - Capital actuel - Marge moyenne --- ## 📲 G. Résumé automatique Telegram Envoi quotidien ou hebdomadaire : Exemple : 📊 Résumé des ventes – 28 Mars 🛍 Produits : 120 000 FCFA 🛠 Services : 30 000 FCFA 💰 Total : 150 000 FCFA 📈 Bénéfice estimé : 45 000 FCFA Envoi via : - Telegram Bot car gratuit. --- # 🏗 3️⃣ Architecture Technique ## Backend - Django - API REST interne - Logique comptable intégrée ## Base de données - PostgreSQL - Base de production sécurisée --- # 🧠 4️⃣ Pourquoi Mobile-First est stratégique ✔ Le vendeur travaille depuis la boutique ✔ Pas besoin d’ordinateur ✔ Accessible partout ✔ Adapté au contexte africain (usage mobile dominant) ✔ Peut évoluer vers une vraie application mobile plus tard --- # 🔐 4️⃣ Sécurité - Authentification sécurisée - Accès administrateur protégé - HTTPS - Sauvegarde automatique base de données # 🎯 9️⃣ Valeur ajoutée pour le porteur du projet - Vision claire du bénéfice réel - Fin des pertes invisibles - Suivi précis du stock - Historique client structuré - Décision basée sur données - Gain de temps quotidien - Professionnalisation du business 1. **Caching** : Utilisez Redis pour les tableaux de bord fréquemment accédés 2. **API REST** : Prévoyez Django REST Framework pour éventuelle app mobile native 3. **Tests** : Écrivez des tests unitaires pour les calculs de bénéfices 4. **Backup** : Configurez pg_dump automatique quotidien 5. **Logging** : Logguez toutes les opérations financières importantes --- # 🧠 Conclusion Ce projet n’est pas juste une application. C’est : - Un outil de gestion - Un outil de pilotage financier - Un outil d’automatisation - Un futur levier de croissance On va realiser ce projet etape par étape