"""Telefoner (MDM): klargøring af driftstelefoner direkte fra IN-BASE – uden server.

IN-BASE viser en QR-kode og starter en midlertidig webserver på pc'en (samme
Wi-Fi som telefonen). Telefonen henter styrings-appen (assets/mdm), som låser
og klargør den offline og til sidst melder tilbage. Se docs/MDM_OPSAETNING.md.
"""
