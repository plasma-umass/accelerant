use perfparser::Parser;

fn main() {
    let parser = Parser::new(std::io::stdin());
    for event in parser {
        println!("{:?}", event);
    }
}
