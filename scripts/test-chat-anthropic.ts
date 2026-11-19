import {ChatAnthropic} from "@langchain/anthropic";
import {z} from "zod";

const schema = z.object({
    answer: z.boolean(),
    reason: z.string(),
});
const model = new ChatAnthropic({
    model:"claude-haiku-4-5",
    temperature: 0,
}).withStructuredOutput(schema);

async function main(){
    const result = await model.invoke("Is the sky blue on a clear day? Answer with the schema.");
    console.log(result);
}

main();