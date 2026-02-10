# MSI-a Documentation - Master Index

Welcome to the MSI-a documentation. This directory contains all technical documentation organized by category.

---

## 📁 Documentation Structure

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| **[architecture/](architecture/)** | System architecture (current + legacy) | v2.0 mode-based architecture, diagrams |
| **[decisions/](decisions/)** | Architecture Decision Records (ADRs) | All architectural decisions with context |
| **[plans/](plans/)** | Implementation plans | Active plans + completed archive |
| **[coding-standards/](coding-standards/)** | Coding conventions & patterns | Python, TypeScript, DB, Security, Testing |
| **[deployment/](deployment/)** | Deployment history & reports | Phase deployments, rollouts |
| **[bugs/](bugs/)** | Bug fixes documentation | Fixed bugs with root cause analysis |
| **[testing/](testing/)** | Testing documentation | Test suites, validation, results |
| **[sessions/](sessions/)** | Development session notes | Session summaries by date |
| **[research/](research/)** | Technical research & spikes | Investigations, proof-of-concepts |
| **[archive/](archive/)** | Historical/obsolete docs | Old architectures, completed migrations |

---

## 🚀 Quick Start

### For New Developers

1. **Understand the system**: Start with [architecture/current/00-overview.md](architecture/current/00-overview.md)
2. **Learn coding standards**: Read [coding-standards/README.md](coding-standards/README.md)
3. **Check recent decisions**: Browse [decisions/](decisions/) for context on architectural choices
4. **Review active plans**: See [plans/active/](plans/active/) for ongoing work

### For AI Agents

1. **Before making changes**: Check [decisions/](decisions/) for relevant ADRs
2. **For coding**: Load appropriate skills from `coding-standards/`
3. **For architecture**: Reference [architecture/current/](architecture/current/)
4. **For patterns**: See [coding-standards/](coding-standards/) by domain

---

## 📚 Key Documents

### Architecture
- [Current Architecture (v2.0)](architecture/current/00-overview.md) - Mode-based conversation system
- [Legacy FSM Archive](architecture/legacy/fsm-v1-archive.md) - Historical FSM v1.0 documentation

### Standards
- [General Standards](coding-standards/00-general.md) - Fundamental rules for all components
- [Python Backend](coding-standards/01-python-backend.md) - FastAPI + SQLAlchemy patterns
- [Agent Architecture](coding-standards/03-agent-architecture.md) - LangGraph + Modes patterns
- [Frontend React](coding-standards/04-frontend-react.md) - Next.js 16 + Radix UI patterns

### Decisions
- [ADR Index](decisions/README.md) - All Architecture Decision Records
- [ADR Template](decisions/template.md) - Template for new ADRs

### Plans
- [Active Plans](plans/active/) - Currently in progress
- [Completed Plans](plans/completed/) - Archive of finished plans

---

## 🔍 Finding Information

### By Topic

| Topic | Location |
|-------|----------|
| How the agent conversation works | [architecture/current/02-modes-overview.md](architecture/current/02-modes-overview.md) |
| How to write API routes | [coding-standards/01-python-backend.md](coding-standards/01-python-backend.md) |
| How to write database models | [coding-standards/02-database.md](coding-standards/02-database.md) |
| How to write agent tools | [coding-standards/03-agent-architecture.md](coding-standards/03-agent-architecture.md) |
| How to write React components | [coding-standards/04-frontend-react.md](coding-standards/04-frontend-react.md) |
| Security best practices | [coding-standards/05-security.md](coding-standards/05-security.md) |
| Why we use Redis Streams | [decisions/001-redis-streams.md](decisions/001-redis-streams.md) |
| Why we use dynamic prompts | [decisions/002-dynamic-prompts.md](decisions/002-dynamic-prompts.md) |

### By Date

- **Deployments**: See [deployment/](deployment/) for chronological deployment history
- **Sessions**: See [sessions/2026-02/](sessions/2026-02/) for development session notes
- **Bug Fixes**: See [bugs/fixed/](bugs/fixed/) for resolved bugs

---

## 🛠️ Maintenance

### Adding New Documentation

1. **Architecture changes**: Create an ADR in [decisions/](decisions/)
2. **New features**: Create a plan in [plans/active/](plans/active/)
3. **Bug fixes**: Document in [bugs/fixed/](bugs/fixed/) after resolution
4. **Deployments**: Add summary to [deployment/](deployment/)
5. **Sessions**: Add notes to [sessions/YYYY-MM/](sessions/)

### Updating Existing Documentation

1. Check if an ADR needs updating (if decision changed)
2. Update relevant coding standards if patterns changed
3. Archive obsolete docs to [archive/](archive/)
4. Update this README if structure changed

---

## 📞 Support

For questions about:
- **Architecture**: Review [architecture/](architecture/) and [decisions/](decisions/)
- **Implementation patterns**: See [coding-standards/](coding-standards/)
- **Active work**: Check [plans/active/](plans/active/)
- **Historical context**: Browse [archive/](archive/)

---

**Last Updated**: February 2026  
**Version**: 2.0 (Mode-based architecture)
