#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: set ts=2 sw=2 noet:

import sys
from nlp_util import coreference_reading, coreference_rendering, coreference, init

if __name__ == '__main__':
	init.argcheck(sys.argv, 4, 5, "Print coreference resolution errors", "<prefix> <gold_dir> <test> [resolve span errors first? T | F]")

	auto = coreference_reading.read_conll_coref_system_output(sys.argv[3])
	gold = coreference_reading.read_conll_matching_files(auto, sys.argv[2])

	out_cluster_errors = open(sys.argv[1] + '.cluster_errors', 'w')
	out_cluster_context = open(sys.argv[1] + '.cluster_context', 'w')
	out_cluster_missing = open(sys.argv[1] + '.cluster_missing', 'w')
	out_cluster_extra = open(sys.argv[1] + '.cluster_extra', 'w')
	out_mention_list = open(sys.argv[1] + '.mention_list', 'w')
	out_mention_text = open(sys.argv[1] + '.mention_text', 'w')
	out_files = [out_cluster_errors,
	             out_cluster_context,
	             out_cluster_missing,
	             out_cluster_extra,
	             out_mention_list,
	             out_mention_text]
	init.header(sys.argv, out_files)

	for function, outfile in [
		(coreference_rendering.print_mention_text, out_mention_text),
		(coreference_rendering.print_mention_list, out_mention_list),
		(coreference_rendering.print_cluster_errors, out_cluster_errors),
		(coreference_rendering.print_cluster_errors, out_cluster_context),
		(coreference_rendering.print_cluster_extra, out_cluster_extra),
		(coreference_rendering.print_cluster_missing, out_cluster_missing)
		]:
		instructions = function.__doc__.split('\n')
		instructions = ['# ' + inst for inst in instructions]
		print >> outfile, '\n'.join(instructions)

	# Define an order
	order = []
	for doc in auto:
		for part in auto[doc]:
			order.append((doc, part))
	order.sort()

	for doc, part in order:
		# Setup
		for out in out_files:
			print >> out, "\n# %s %s\n" % (doc, part)

		text = gold[doc][part]['text']

		gold_parses = gold[doc][part]['parses']
		gold_heads = gold[doc][part]['heads']
		gold_mentions = gold[doc][part]['mentions']
		gold_clusters = gold[doc][part]['clusters']

		auto_mentions = auto[doc][part]['mentions']
		auto_clusters = auto[doc][part]['clusters']

		gold_cluster_set = coreference.set_of_clusters(gold_clusters)
		auto_cluster_set = coreference.set_of_clusters(auto_clusters)
		gold_mention_set = coreference.set_of_mentions(gold_clusters)
		auto_mention_set = coreference.set_of_mentions(auto_clusters)

		if len(sys.argv) > 4 and sys.argv[4] == 'T':
			coreference_rendering.match_boundaries(gold_mention_set, auto_mention_set, auto_mentions, auto_clusters, auto_cluster_set, text, gold_parses, gold_heads)

		# Coloured mention output
		coreference_rendering.print_mention_list(out_mention_list, gold_mentions, auto_mention_set, gold_parses, gold_heads, text)
		coreference_rendering.print_mention_text(out_mention_text, gold_mentions, auto_mention_set, gold_parses, gold_heads, text)

		# Coloured cluster output, grouped
		groups = coreference.confusion_groups(gold_mentions, auto_mentions, gold_clusters, auto_clusters)

		covered = coreference_rendering.print_cluster_errors(groups, out_cluster_errors, out_cluster_context, text, gold_parses, gold_heads, auto_clusters, gold_clusters, gold_mentions)
		print >> out_cluster_errors, "Entirely missing or extra\n"
		print >> out_cluster_context, "Entirely missing or extra\n"
		coreference_rendering.print_cluster_missing(out_cluster_errors, out_cluster_context, out_cluster_missing, text, gold_cluster_set, covered, gold_parses, gold_heads)
		coreference_rendering.print_cluster_extra(out_cluster_errors, out_cluster_context, out_cluster_extra, text, auto_cluster_set, covered, gold_parses, gold_heads)

