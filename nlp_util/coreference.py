#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set ts=2 sw=2 noet:

import sys
from collections import defaultdict
import string

from .head_finder import get_head

# TODO: Look into semantic head finding (current is syntactically biased)

def confusion_groups(gold_mentions, auto_mentions, gold_clusters, auto_clusters):
    groups = []
    mentions = set()
    for mention in gold_mentions:
        mentions.add(mention)
    for mention in auto_mentions:
        mentions.add(mention)
    while len(mentions) > 0:
        # Choose a random mention and DFS to create the confusion group
        auto = []
        gold = []
        seed = mentions.pop()
        stack = []
        seen_gold = set()
        seen_auto = set()
        if seed in gold_mentions:
            stack.append((gold_mentions[seed], True))
            seen_gold.add(stack[0][0])
        else:
            stack.append((auto_mentions[seed], False))
            seen_auto.add(stack[0][0])

        while len(stack) > 0:
            cluster, is_gold = stack.pop()
            if is_gold:
                gold.append(set(gold_clusters[cluster]))
                for mention in gold_clusters[cluster]:
                    auto_cluster = auto_mentions.get(mention)
                    if auto_cluster is not None:
                        if auto_cluster not in seen_auto:
                            stack.append((auto_cluster, False))
                            seen_auto.add(auto_cluster)
                    mentions.discard(mention)
            else:
                auto.append(set(auto_clusters[cluster]))
                for mention in auto_clusters[cluster]:
                    gold_cluster = gold_mentions.get(mention)
                    if gold_cluster is not None:
                        if gold_cluster not in seen_gold:
                            stack.append((gold_cluster, True))
                            seen_gold.add(gold_cluster)
                    mentions.discard(mention)
        groups.append((auto, gold))
    return groups

def mention_head(mention, text, parses, heads, default_last=True):
    sentence, start, end = mention
    node = parses[sentence].get_nodes('lowest', start, end)
    if node is None:
        if default_last:
            node = parses[sentence].get_nodes('lowest', end - 1, end)
        else:
            return None
    return get_head(heads[sentence], node)

def mention_type(mention, text, parses, heads):
    head_span, head_word, head_pos = mention_head(mention, text, parses, heads)
    if mention[2] - mention[1] == 1 and (head_pos in ["PRP", "PRP$", "WP", "WP$", "WDT", "WRB", "DT"] or head_word.lower() in pronoun_properties):
        return "pronoun"
    elif head_pos in ["NNP", "NNPS"]:
        return "name"
    else:
        return 'nominal'

def mention_text(mention, text):
    sentence, start, end = mention
    ans = text[sentence][start:end]
    return ' '.join(ans)

def set_of_clusters(clusters):
    ans = set()
    for cluster in clusters:
        mentions = clusters[cluster][:]
        mentions.sort()
        ans.add(tuple(mentions))
    return ans

def set_of_mentions(clusters):
    ans = set()
    for cluster in clusters:
        for mention in clusters[cluster]:
            ans.add(mention)
    return ans

def hash_clustering(clustering):
    clustering = [list(v) for v in clustering]
    for i in range(len(clustering)):
        clustering[i].sort()
        clustering[i] = tuple(clustering[i])
    clustering.sort()
    return tuple(clustering)

PRO_FIRST = 1
PRO_SECOND = 2
PRO_THIRD = 3
PRO_PLURAL = 2
PRO_SINGLE = 1
PRO_UNKNOWN = 0
PRO_FEMALE = 1
PRO_MALE = 2
PRO_NEUTER = 3

def pronoun_properties_text(text):
    gender = 'unknown'
    number = 'unknown'
    person = 'unknown'
    text = text.lower()
    if text in pronoun_properties:
        nums = pronoun_properties[text]

        if nums[0] == PRO_FEMALE:
            gender = 'female'
        elif nums[0] == PRO_MALE:
            gender = 'male'
        elif nums[0] == PRO_NEUTER:
            gender = 'neuter'

        if nums[1] == PRO_SINGLE:
            number = 'single'
        elif nums[1] == PRO_PLURAL:
            number = 'plural'

        if nums[2] == PRO_FIRST:
            gender = 'first'
        elif nums[2] == PRO_SECOND:
            gender = 'second'
        elif nums[2] == PRO_THIRD:
            gender = 'third'

    return gender, number, person

# Notes:
# Plural and singular are defined in terms of the property of the entity being
# denoted.
pronoun_properties = {
    "her": (PRO_FEMALE, PRO_SINGLE, PRO_THIRD),
    "hers": (PRO_FEMALE, PRO_SINGLE, PRO_THIRD),
    "herself": (PRO_FEMALE, PRO_SINGLE, PRO_THIRD),
    "she": (PRO_FEMALE, PRO_SINGLE, PRO_THIRD),
    "he": (PRO_MALE, PRO_SINGLE, PRO_THIRD),
    "him": (PRO_MALE, PRO_SINGLE, PRO_THIRD),
    "himself": (PRO_MALE, PRO_SINGLE, PRO_THIRD),
    "his": (PRO_MALE, PRO_SINGLE, PRO_THIRD),
    "our": (PRO_UNKNOWN, PRO_PLURAL, PRO_FIRST),
    "ours": (PRO_UNKNOWN, PRO_PLURAL, PRO_FIRST),
    "yours": (PRO_UNKNOWN, PRO_SINGLE, PRO_SECOND),
    "ourselves": (PRO_UNKNOWN, PRO_PLURAL, PRO_FIRST),
    "yourselves": (PRO_UNKNOWN, PRO_PLURAL, PRO_SECOND),
    "they": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD), # Note, technically plural
    "their": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD),
    "theirs": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD),
    "them": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "'em": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "em": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "themselves": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "us": (PRO_UNKNOWN, PRO_PLURAL, PRO_FIRST),
    "we": (PRO_UNKNOWN, PRO_PLURAL, PRO_FIRST),
    "whoever": (PRO_UNKNOWN, PRO_SINGLE, PRO_UNKNOWN),
    "whomever": (PRO_UNKNOWN, PRO_SINGLE, PRO_UNKNOWN),
    "whose": (PRO_UNKNOWN, PRO_SINGLE, PRO_UNKNOWN),
    "i": (PRO_UNKNOWN, PRO_SINGLE, PRO_FIRST),
    "me": (PRO_UNKNOWN, PRO_SINGLE, PRO_FIRST),
    "mine": (PRO_UNKNOWN, PRO_SINGLE, PRO_FIRST),
    "my": (PRO_UNKNOWN, PRO_SINGLE, PRO_FIRST),
    "myself": (PRO_UNKNOWN, PRO_SINGLE, PRO_FIRST),
    "one": (PRO_UNKNOWN, PRO_SINGLE, PRO_FIRST),
    "thyself": (PRO_UNKNOWN, PRO_SINGLE, PRO_SECOND),
    "ya": (PRO_UNKNOWN, PRO_SINGLE, PRO_SECOND),
    "you": (PRO_UNKNOWN, PRO_SINGLE, PRO_SECOND),
    "your": (PRO_UNKNOWN, PRO_SINGLE, PRO_SECOND),
    "yourself": (PRO_UNKNOWN, PRO_SINGLE, PRO_SECOND),
    "it": (PRO_NEUTER, PRO_SINGLE, PRO_THIRD),
    "its": (PRO_NEUTER, PRO_SINGLE, PRO_THIRD),
    "itself": (PRO_NEUTER, PRO_SINGLE, PRO_THIRD),
    "what": (PRO_NEUTER, PRO_SINGLE, PRO_UNKNOWN),
    "when": (PRO_NEUTER, PRO_SINGLE, PRO_UNKNOWN),
    "where": (PRO_NEUTER, PRO_SINGLE, PRO_UNKNOWN),
    "which": (PRO_NEUTER, PRO_SINGLE, PRO_UNKNOWN),
    "how": (PRO_NEUTER, PRO_SINGLE, PRO_UNKNOWN),

    "everybody": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "everyone": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "anybody": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD),
    "anyone": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD),
    "somebody": (PRO_UNKNOWN, PRO_SINGLE, PRO_THIRD),
    "someone": (PRO_UNKNOWN, PRO_SINGLE, PRO_THIRD),
    "nobody": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD),

    "all": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "few": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "several": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "some": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "many": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "most": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "none": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD),
    "noone": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_THIRD),

    "that": (PRO_UNKNOWN, PRO_SINGLE, PRO_THIRD),
    "this": (PRO_UNKNOWN, PRO_SINGLE, PRO_THIRD),
    "these": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),
    "those": (PRO_UNKNOWN, PRO_PLURAL, PRO_THIRD),

    "whatever": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_UNKNOWN),
    "who": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_UNKNOWN),
    "whom": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_UNKNOWN),

    "something": (PRO_UNKNOWN, PRO_SINGLE, PRO_UNKNOWN),
    "nothing": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_UNKNOWN),
    "everything": (PRO_UNKNOWN, PRO_UNKNOWN, PRO_UNKNOWN)

###another
###any
###anything
###both
###each
###eachother
###either
###little
###more
###much
###neither
###oneanother
###other
###others
###whichever
}

if __name__ == '__main__':
    print("Running doctest")
    import doctest
    doctest.testmod()

