def allowed(document, groups):
    return bool(set(document.acl) & set(groups))


def visible_documents(documents, groups):
    return [document for document in documents if allowed(document, groups)]


def filter_decisions(decisions, state, groups):
    visible_urls = {document.url for document in visible_documents(state.list_documents(), groups)}
    result = []
    for decision in decisions:
        evidence = state.evidence_for(decision.id)
        if any(item["url"] in visible_urls for item in evidence):
            result.append(decision)
    return result
