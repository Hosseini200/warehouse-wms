
```markdown
# Warehouse WMS - Development Workflow

## Purpose

This document defines the standard development workflow for Warehouse WMS.

The goal is to ensure that all future changes are developed, reviewed, tested, and deployed safely without directly modifying the production environment.

---

# Environment Structure

## Production Environment

Production is the live system used by the customer.

Production URL:

https://wms.daroo100.com/


Production rules:

- Never modify production code directly.
- Never test new features on production.
- Always create a backup before deployment.
- Every production change must come from an approved Git version.

---

# Git Repository Structure

Repository:

https://github.com/Hosseini200/warehouse-wms.git


Branches:

```

main
|
└── Production versions

develop
|
└── Integration and testing branch

feature/*
|
└── Individual development tasks

```

---

# Branch Rules

## main Branch

Purpose:

Production-ready code only.


Rules:

- No direct development.
- No unfinished features.
- Only tested versions are merged here.
- Every merge represents a deployable version.

Example:

```

main
|
└── Production Baseline v1

```

---

## develop Branch

Purpose:

Development integration branch.


Rules:

- All completed features are merged here first.
- Integration testing happens here.
- Production deployment starts from tested develop versions.

---

## feature Branches

Purpose:

Individual changes and customer requests.


Naming convention:

```

feature/<short-description>

```

Examples:

```

feature/inventory-report
feature/add-user-permission
feature/packaging-management

```

---

# Development Process

Every new request follows this workflow:

```

Customer Requirement

```
    ↓
```

Requirement Analysis

```
    ↓
```

Create Feature Branch

```
    ↓
```

Backend Changes

```
    ↓
```

Frontend Changes

```
    ↓
```

Database Changes

```
    ↓
```

Testing

```
    ↓
```

Merge to develop

```
    ↓
```

Production Approval

```
    ↓
```

Merge to main

```
    ↓
```

Deploy

````

---

# Starting a New Feature

Always start from the latest develop branch.

Commands:

```bash
git checkout develop

git pull
````

Create feature branch:

```bash
git checkout -b feature/feature-name
```

---

# Making Changes

After modifying files:

Check status:

```bash
git status
```

Review changed files before commit.

Add changes:

```bash
git add .
```

Create commit:

```bash
git commit -m "Describe the change"
```

Examples:

Good:

```
Add inventory filtering by warehouse
```

Bad:

```
changes
update
fix
```

---

# Sending Changes to GitHub

Push feature branch:

```bash
git push -u origin feature/feature-name
```

---

# Merging Feature to Develop

After testing:

Switch to develop:

```bash
git checkout develop
```

Update:

```bash
git pull
```

Merge:

```bash
git merge feature/feature-name
```

Push:

```bash
git push
```

---

# Production Release Process

Before production deployment:

Checklist:

* Backend tested
* Frontend tested
* Database migration reviewed
* No critical errors
* Backup completed

Merge develop into main:

```bash
git checkout main

git pull

git merge develop

git push
```

---

# Rollback Strategy

Every production release must have a Git commit reference.

To inspect history:

```bash
git log --oneline
```

Example:

```
d8f2636 Production Baseline v1
```

Rollback is performed by returning to a known stable commit.

---

# Database Change Rules

Database changes must:

* Have migration files.
* Be reviewed before execution.
* Never modify production database manually without backup.

Migration location:

```
migrations/
```

Naming example:

```
YYYYMMDD_description_up.sql

YYYYMMDD_description_down.sql
```

---

# Environment Files

Sensitive files must never enter Git:

Examples:

```
.env
database passwords
secret keys
API credentials
```

These files must remain local/server-only.

---

# AI Development Rules

When using AI for development:

1. Always provide the current Git branch.
2. Always specify the requested feature.
3. Never ask AI to modify production directly.
4. Review generated code before commit.
5. Test before merging.
6. Commit meaningful changes.

---

# Commit Rules

Each commit should represent one logical change.

Examples:

Good:

```
Add production batch validation
Fix transfer approval API
Update inventory dashboard UI
```

Bad:

```
final
test
update everything
```

---

# Current Project Baseline

Initial production baseline:

Commit:

```
d8f2636
```

Message:

```
Production Baseline v1 - 2026-10-01
```

Documentation baseline:

Commit:

```
576d4b0
```

Message:

```
Add project baseline documentation
```

---

# Golden Rule

Never change production directly.

Always follow:

```
Production
    ↓
Git Branch
    ↓
Development
    ↓
Testing
    ↓
Production Release
```
