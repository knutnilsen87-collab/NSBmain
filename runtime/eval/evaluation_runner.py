class EvaluationRunner:

    def __init__(self, decoder):
        self.decoder = decoder

    def run(self, dataset):
        results = []
        for sample in dataset:
            text = self.decoder.decode(sample["audio"])
            results.append({
                "ref": sample["reference"],
                "hyp": text
            })
        return results
