UN General Assembly Scraping Plan (single session, e.g. GA78)

1. Overall architecture

Think in three layers:
	1.	Raw artifacts
	•	PDFs, HTML pages, JSON from APIs.
	•	Stored on disk, minimally indexed.
	2.	Parsed metadata
	•	Tables or JSON objects representing documents, relationships, and votes.
	•	No graph database needed initially.
	3.	Graph view
	•	Built on top of parsed metadata for reasoning (agenda item to drafts to votes to resolutions).

⸻

2. High-level scraping steps for a single GA session

Target: one GA session (e.g. 78th), then generalize.
	1.	Fetch agenda and allocation
	•	A/78/251 (Agenda)
	•	A/78/251/Rev.1 (Agenda + list of adopted resolutions/decisions per item)
	•	A/78/252 (Allocation of items to committees or plenary)
	2.	Fetch all draft resolutions/decisions
	•	Plenary drafts: A/78/L.*
	•	Committee drafts: A/C.1/78/L., A/C.2/78/L., …, A/C.6/78/L.*
	•	Includes amendments (titles say “amendment to draft resolution A/78/L.48”).
	3.	Fetch all resolutions and decisions
	•	Resolutions: A/RES/78/*
	•	Decisions: A/DEC/78/* (often referenced as decision 78/xxx in A/78/251/Rev.1)
	4.	Fetch committee reports
	•	First Committee: A/78/40x (e.g., A/78/408)
	•	Third Committee: A/78/45x (e.g., A/78/458 and addenda)
	•	Similar pattern for other committees or by searching “Report of the First/Second/… Committee”.
	5.	Fetch meeting records
	•	Plenary: A/78/PV.* (e.g., A/78/PV.62, A/78/PV.63)
	•	Optionally committee summary records: A/C.3/78/SR.*, etc., for deeper committee-level detail.

⸻

3. Core APIs and URLs to hit

Primary entry point is the UN Digital Library.

3.1 Digital Library search

Base endpoint (JSON format):

https://digitallibrary.un.org/search?format=js

Key parameters:
	•	q: free-text query, e.g. A/78/L.
	•	f[]: filters, examples:
	•	f[]=recordtype:Doc
	•	f[]=recordtype:Vote
	•	f[]=session:78
	•	f[]=symbol:A/RES/78/*

Examples:

List all GA78 resolutions:

https://digitallibrary.un.org/search?format=js&f[]=recordtype:Doc&f[]=symbol:A/RES/78/*

List all GA78 plenary drafts (rough):

https://digitallibrary.un.org/search?format=js&q=A/78/L.&f[]=recordtype:Doc

List GA78 Third Committee drafts:

https://digitallibrary.un.org/search?format=js&q=A/C.3/78/L.&f[]=recordtype:Doc

You refine later using doctype and session fields from the JSON.

3.2 Digital Library record metadata and file URLs

Given a record id (e.g. 4082677), you can request:

JSON metadata:

https://digitallibrary.un.org/record/4082677/export/json

MARC XML:

https://digitallibrary.un.org/record/4082677/export/xm

These typically include:
	•	symbol (e.g. A/78/L.48, A/78/251/Rev.1, A/RES/78/264)
	•	title
	•	agenda information (e.g. A/78/251 14 Culture of peace.)
	•	session
	•	document type (draft resolution, resolution, report of the First Committee, etc.)
	•	date
	•	list of files with URLs such as:
/record/4082677/files/A_79_PV.55_%28Resumption_1%29-EN.pdf?download=1

To download the file:

https://digitallibrary.un.org/record/4082677/files/A_79_PV.55_%28Resumption_1%29-EN.pdf?download=1

Same pattern works for:
	•	A/78/251-EN.pdf
	•	A/78/251_Rev.1-EN.pdf
	•	A/78/L.48-EN.pdf
	•	A/RES/78/264-EN.pdf
	•	A/78/408-EN.pdf
	•	A/78/PV.62-EN.pdf

When a file is missing or access-controlled, you can optionally try docs.un.org for that symbol, but the Digital Library file URLs are the primary path.

⸻

4. Document types to handle

At a minimum, for one GA session you need to handle:
	1.	Agenda and allocation
	•	A/78/251
	•	A/78/251/Rev.1 (links agenda items to resolutions and decisions)
	•	A/78/252 (allocation to committees)
	2.	Draft resolutions and draft decisions
	•	Plenary: A/78/L.n
	•	Main Committees: A/C.n/78/L.m (First–Sixth committees)
	•	Amendments: same patterns, with titles like “amendment to draft resolution A/78/L.48”
	3.	Resolutions
	•	A/RES/78/xxx
	•	Resolution metadata usually includes:
	•	Draft symbol (e.g. A/78/L.48)
	•	Committee report symbol (e.g. A/78/408)
	•	Meeting record symbol (e.g. A/78/PV.62)
	•	Vote summary (numbers, sometimes link to Voting Data)
	4.	Decisions
	•	A/DEC/78/xxx (often referenced in A/78/251/Rev.1 as decision 78/562, etc.)
	•	Used mostly for procedural or appointment actions, but can also be substantive.
	•	Same pattern: symbol, agenda item, date; sometimes votes.
	5.	Committee reports
	•	Reports “on the report of the First/Second/… Committee”:
	•	A/78/40x (First Committee)
	•	A/78/45x (Third Committee), with addenda
	•	Resolution chapeaux explicitly cite these (e.g. “on the report of the First Committee (A/78/408, para. 114)”).
	6.	Meeting records
	•	Plenary verbatim records: A/78/PV.n
	•	Optionally committee summary records: A/C.3/78/SR.n, A/C.1/78/SR.n, etc.
	•	Used to recover:
	•	Adoption without vote
	•	Vote tallies on amendments and drafts that never became resolutions
	•	Oral revisions

⸻

5. How to systematically enumerate instead of guessing symbols

For a given session S (e.g. 78):
	1.	Agenda and allocation
	•	Explicitly fetch records for A/S/251, A/S/251/Rev.1, A/S/252 by symbol via search.
	2.	Drafts
	•	Use search with q = A/S/L. and recordtype:Doc to find all plenary drafts A/78/L.*
	•	For committees, search q = A/C.n/S/L. for n = 1…6.
	•	Optional: refine with doctype field (Draft resolution) and session:78 in filters.
	3.	Resolutions and decisions
	•	Search: f[]=recordtype:Doc, f[]=symbol:A/RES/78/*
	•	Search: f[]=recordtype:Doc, f[]=symbol:A/DEC/78/* (if you want decisions explicitly).
	4.	Committee reports
	•	Search by session and title, e.g.
	•	q = “Report of the First Committee”, f[]=session:78
	•	q = “Report of the Third Committee”, f[]=session:78
	•	Or, after you have resolution records, read the Committee report field from each resolution’s metadata and back-fill.
	5.	Meeting records
	•	Via resolution metadata: for each A/RES/78/x, read the Meeting record field (e.g. A/78/PV.62).
	•	Optionally do a broader search for A/78/PV.* if you want all plenary meetings for that session.
	6.	Voting data
	•	Use the Voting Data collection (recordtype:Vote, session:78) and filter by target symbol or agenda item.

You never need to randomly try A/78/L.1, L.2, etc. You always list what exists via search, then traverse record metadata to find links.

⸻

6. Flow of an agenda item (conceptual pipeline)

This is the conceptual graph for one GA item. Not all edges exist for every item, but the pattern is stable.
	1.	Agenda and allocation
	•	Session adopts agenda A/78/251.
	•	Allocation A/78/252 assigns item N to plenary or a specific committee.
	2.	Committee stage (if allocated)
	•	Item handled in Main Committee n.
	•	States table committee drafts A/C.n/78/L.* (and amendments).
	•	Committee debates, revises, and votes on drafts and amendments.
	•	Outcomes recorded in:
	•	Committee meeting records (A/C.n/78/SR.*)
	•	“Status of draft proposals” tables
	•	Committee produces a report A/78/40x or A/78/45x transmitting the recommended text.
	3.	Plenary stage
	•	Plenary receives:
	•	Committee report (for committee-handled items)
	•	Or directly a plenary draft A/78/L.* (for plenary-only items, like some high-profile political items).
	•	Plenary considers draft and any plenary amendments (A/78/L.* with “amendment to draft resolution…”).
	•	Plenary voting (or consensus) recorded in:
	•	Meeting record A/78/PV.m
	•	Voting Data record (if roll-call)
	4.	Outcome
	•	If adopted as a resolution:
	•	Document A/RES/78/xxx created.
	•	Resolution metadata ties back to:
	•	Draft symbol
	•	Committee report symbol
	•	Meeting record symbol
	•	Agenda information
	•	Vote summary
	•	If adopted as a decision:
	•	Document A/DEC/78/xxx created.
	•	Similar linkage, usually procedural or follow-up.
	•	If an amendment or draft is rejected:
	•	No A/RES/78/xxx for that symbol.
	•	Rejection recorded in the meeting record and press; sometimes in Voting Data.

For your data model and eventual gym:
	•	Backwards: agenda item → committee (from A/78/252) → draft(s) (from draft metadata agenda_information).
	•	Sideways within committee: base draft ↔ amendments ↔ revisions.
	•	Forwards: draft → committee report → plenary meeting → resolution/decision or “rejected” event.

All of this can be discovered and stored using Digital Library search and record metadata, plus targeted PDF/HTML parsing where needed for clause content and detailed vote descriptions.